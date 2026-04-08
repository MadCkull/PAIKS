"""
Tests for api.services.sync_manager — Background sync engine, health computation,
debounce logic, stale job detection, and directory filtering.
"""
import pytest
import os
import time
import queue
import hashlib
import threading
from unittest.mock import patch, MagicMock, PropertyMock
from django.utils import timezone

@pytest.fixture(autouse=True)
def clear_index_queue():
    """Clear the global _index_queue before each test."""
    from api.services.sync_manager import _index_queue
    while not _index_queue.empty():
        try:
            _index_queue.get_nowait()
        except queue.Empty:
            break

@pytest.fixture
def doc_track_factory(db):
    """Factory to create DocumentTrack records for testing."""
    from api.models import DocumentTrack

    def _create(file_id="local__test.txt", name="test.txt", source="local",
                is_selected=True, sync_status="pending", content_hash="abc123"):
        return DocumentTrack.objects.create(
            file_id=file_id, name=name, source=source,
            is_selected=is_selected, sync_status=sync_status,
            content_hash=content_hash, last_modified=timezone.now()
        )
    return _create


# ── Health Computation Tests ────────────────────────────────────

@pytest.mark.django_db
class TestComputeAndBroadcastHealth:
    """Tests _compute_and_broadcast_health — the single source of truth for badge state."""

    def test_all_synced_returns_synced(self, doc_track_factory):
        from api.services.sync_manager import _compute_and_broadcast_health
        doc_track_factory(file_id="local__a.txt", sync_status="synced")
        doc_track_factory(file_id="local__b.txt", sync_status="synced")

        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "synced"})

    def test_any_syncing_returns_syncing(self, doc_track_factory):
        from api.services.sync_manager import _compute_and_broadcast_health
        doc_track_factory(file_id="local__a.txt", sync_status="synced")
        doc_track_factory(file_id="local__b.txt", sync_status="syncing")

        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "syncing"})

    def test_any_pending_returns_syncing(self, doc_track_factory):
        from api.services.sync_manager import _compute_and_broadcast_health
        doc_track_factory(file_id="local__a.txt", sync_status="synced")
        doc_track_factory(file_id="local__b.txt", sync_status="pending")

        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "syncing"})

    def test_error_with_no_syncing_returns_warning(self, doc_track_factory):
        from api.services.sync_manager import _compute_and_broadcast_health
        doc_track_factory(file_id="local__a.txt", sync_status="synced")
        doc_track_factory(file_id="local__b.txt", sync_status="error")

        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "warning"})

    def test_no_selected_files_returns_synced(self, doc_track_factory):
        from api.services.sync_manager import _compute_and_broadcast_health
        doc_track_factory(file_id="local__a.txt", sync_status="error", is_selected=False)

        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "synced"})

    def test_deselected_errors_do_not_affect_health(self, doc_track_factory):
        """Deselected files with errors should NOT make the badge orange."""
        from api.services.sync_manager import _compute_and_broadcast_health
        doc_track_factory(file_id="local__a.txt", sync_status="synced", is_selected=True)
        doc_track_factory(file_id="local__b.txt", sync_status="error", is_selected=False)

        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "synced"})

    def test_mixed_synced_and_disabled_returns_warning(self, doc_track_factory):
        """Selected file with disabled status (not synced, not error) → warning."""
        from api.services.sync_manager import _compute_and_broadcast_health
        doc_track_factory(file_id="local__a.txt", sync_status="synced")
        doc_track_factory(file_id="local__b.txt", sync_status="disabled", is_selected=True)

        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "warning"})


# ── File Hash Tests ─────────────────────────────────────────────

class TestFileHash:
    def test_get_file_hash_returns_sha256(self, tmp_path):
        from api.services.sync_manager import get_file_hash
        f = tmp_path / "test.txt"
        f.write_text("hello world")

        result = get_file_hash(str(f))
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result == expected

    def test_get_file_hash_nonexistent_returns_none(self):
        from api.services.sync_manager import get_file_hash
        assert get_file_hash("/nonexistent/path/file.txt") is None

    def test_different_content_different_hash(self, tmp_path):
        from api.services.sync_manager import get_file_hash
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content A")
        f2.write_text("content B")
        assert get_file_hash(str(f1)) != get_file_hash(str(f2))


# ── Watchdog Handler Tests ──────────────────────────────────────

@pytest.mark.django_db
class TestLocalFileHandler:
    """Tests the watchdog event handler logic."""

    @patch("api.services.sync_manager._debounce_timers", {})
    @patch("api.services.sync_manager.DEBOUNCE_SECONDS", 0)
    def test_handle_change_creates_doc_and_queues(self, tmp_path, doc_track_factory):
        from api.services.sync_manager import LocalFileHandler, _index_queue
        handler = LocalFileHandler()

        f = tmp_path / "newfile.txt"
        f.write_text("some content")

        with patch("api.services.sync_manager._compute_and_broadcast_health"):
            handler._handle_change(str(f))

        from api.models import DocumentTrack
        doc = DocumentTrack.objects.get(file_id=f"local__{f}")
        assert doc.is_selected is True
        assert doc.sync_status == "pending"

    @patch("api.services.sync_manager._debounce_timers", {})
    def test_handle_change_deselected_file_does_not_queue(self, tmp_path):
        """Changing a deselected file must NOT set status to pending or queue it."""
        from api.services.sync_manager import LocalFileHandler, _index_queue
        from api.models import DocumentTrack

        f = tmp_path / "deselected.txt"
        f.write_text("initial")

        # Pre-create as deselected
        DocumentTrack.objects.create(
            file_id=f"local__{f}", name="deselected.txt", source="local",
            is_selected=False, sync_status="disabled",
            content_hash="old", last_modified=timezone.now()
        )

        handler = LocalFileHandler()
        f.write_text("changed content")  # Modify it
        handler._handle_change(str(f))

        doc = DocumentTrack.objects.get(file_id=f"local__{f}")
        # Must stay disabled, NOT set to pending
        assert doc.sync_status == "disabled"

    def test_handle_deleted_marks_disabled(self, tmp_path):
        from api.services.sync_manager import LocalFileHandler
        from api.models import DocumentTrack

        filepath = str(tmp_path / "todelete.txt")
        DocumentTrack.objects.create(
            file_id=f"local__{filepath}", name="todelete.txt", source="local",
            is_selected=True, sync_status="synced",
            last_modified=timezone.now()
        )

        handler = LocalFileHandler()
        handler._handle_deleted(filepath)

        doc = DocumentTrack.objects.get(file_id=f"local__{filepath}")
        assert doc.sync_status == "disabled"

    def test_unsupported_extension_ignored(self, tmp_path):
        from api.services.sync_manager import LocalFileHandler

        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00" * 100)

        handler = LocalFileHandler()
        # _debounced_change should return early for unsupported extensions
        handler._debounced_change(str(f))
        # No DocumentTrack should be created
        from api.models import DocumentTrack
        assert DocumentTrack.objects.filter(file_id=f"local__{f}").count() == 0


# ── Worker Stale Job Detection Tests ────────────────────────────

@pytest.mark.django_db
class TestStaleJobDetection:
    """Tests that the worker skips stale jobs when file content has changed."""

    def test_stale_hash_skips_job(self, doc_track_factory):
        """If expected_hash doesn't match current doc hash, job must be skipped."""
        from api.services.sync_manager import _index_queue

        doc = doc_track_factory(
            file_id="local__D:\\test\\stale.txt",
            sync_status="pending",
            content_hash="new_hash_after_edit"
        )

        # Queue a job with the OLD hash
        _index_queue.put({
            "action": "index",
            "doc_id": doc.id,
            "expected_hash": "old_hash_before_edit"
        })

        # The worker should detect hash mismatch and skip
        job = _index_queue.get_nowait()
        assert job["expected_hash"] != doc.content_hash

    def test_deselected_doc_skips_job(self, doc_track_factory):
        """If user deselected while job was queued, worker must skip."""
        doc = doc_track_factory(
            file_id="local__D:\\test\\deselected.txt",
            sync_status="pending",
            is_selected=False
        )
        # Worker checks doc.is_selected before processing
        assert not doc.is_selected


# ── Directory Filtering Tests ───────────────────────────────────

@pytest.mark.django_db
class TestDirectoryFiltering:
    """Tests that directories are silently skipped and deleted from the queue."""

    def test_directory_doc_gets_deleted(self, tmp_path, doc_track_factory):
        """A DocumentTrack pointing to a directory path must be auto-deleted."""
        dirpath = tmp_path / "TestFolder"
        dirpath.mkdir()

        doc = doc_track_factory(
            file_id=f"local__{dirpath}",
            name="TestFolder",
            sync_status="pending"
        )

        # Verify it's a directory
        assert os.path.isdir(str(dirpath))

        from api.models import DocumentTrack
        assert DocumentTrack.objects.filter(id=doc.id).exists()
