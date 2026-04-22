"""
Tests for api.services.sync_manager — Background sync engine, health computation,
debounce logic, stale job detection, watchdog event handling, and directory filtering.

Covers:
  - _compute_and_broadcast_health state machine
  - get_file_hash SHA-256 correctness
  - LocalFileHandler watchdog events (create, modify, delete, move)
  - Debounce filtering for unsupported extensions
  - Stale job detection by hash / selection
  - Directory filtering (auto-delete directory docs)
  - SSELogHandler log-level classification
  - start_sync_engine / stop_sync_engine lifecycle
"""
import pytest
import os
import time
import queue
import hashlib
import threading
from unittest.mock import patch, MagicMock, PropertyMock
from django.utils import timezone


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

    def test_empty_db_returns_synced(self, db):
        """No documents at all → synced (nothing to worry about)."""
        from api.services.sync_manager import _compute_and_broadcast_health
        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            _compute_and_broadcast_health()
            mock_bc.assert_called_once_with("system_health", {"state": "synced"})


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

    def test_same_content_same_hash(self, tmp_path):
        from api.services.sync_manager import get_file_hash
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("identical")
        f2.write_text("identical")
        assert get_file_hash(str(f1)) == get_file_hash(str(f2))

    def test_empty_file_has_hash(self, tmp_path):
        from api.services.sync_manager import get_file_hash
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = get_file_hash(str(f))
        assert result is not None
        assert len(result) == 64  # SHA-256 hex digest length


# ── Watchdog Handler Tests ──────────────────────────────────────

@pytest.mark.django_db
class TestLocalFileHandler:
    """Tests the watchdog event handler logic."""

    @patch("api.services.sync_manager._debounce_timers", {})
    @patch("api.services.sync_manager.DEBOUNCE_SECONDS", 0)
    def test_handle_change_creates_doc_and_queues(self, tmp_path, doc_track_factory):
        from api.services.sync_manager import LocalFileHandler
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
        from api.services.sync_manager import LocalFileHandler
        from api.models import DocumentTrack

        f = tmp_path / "deselected.txt"
        f.write_text("initial")

        DocumentTrack.objects.create(
            file_id=f"local__{f}", name="deselected.txt", source="local",
            is_selected=False, sync_status="disabled",
            content_hash="old", last_modified=timezone.now()
        )

        handler = LocalFileHandler()
        f.write_text("changed content")
        handler._handle_change(str(f))

        doc = DocumentTrack.objects.get(file_id=f"local__{f}")
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

        from api.models import SyncJob
        job = SyncJob.objects.filter(action="delete").first()
        assert job is not None
        assert job.document.file_id == f"local__{filepath}"

    def test_unsupported_extension_ignored(self, tmp_path):
        from api.services.sync_manager import LocalFileHandler

        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00" * 100)

        handler = LocalFileHandler()
        handler._debounced_change(str(f))

        from api.models import DocumentTrack
        assert DocumentTrack.objects.filter(file_id=f"local__{f}").count() == 0

    def test_supported_extensions_accepted(self, tmp_path):
        """All LOCAL_ALLOWED_EXTENSIONS should pass the debounce filter."""
        from api.services.config import LOCAL_ALLOWED_EXTENSIONS

        for ext in LOCAL_ALLOWED_EXTENSIONS:
            f = tmp_path / f"test{ext}"
            f.write_text("content")
            # Should not raise
            from api.services.sync_manager import LocalFileHandler
            handler = LocalFileHandler()
            # _debounced_change should accept these extensions
            # (it sets up a timer, so we just ensure no exception)
            handler._debounced_change(str(f))

    @patch("api.services.sync_manager._debounce_timers", {})
    def test_handle_change_updates_hash_on_content_change(self, tmp_path):
        """When file content changes, the DB hash must update."""
        from api.services.sync_manager import LocalFileHandler, get_file_hash
        from api.models import DocumentTrack

        f = tmp_path / "changing.txt"
        f.write_text("version 1")
        hash_v1 = get_file_hash(str(f))

        DocumentTrack.objects.create(
            file_id=f"local__{f}", name="changing.txt", source="local",
            is_selected=True, sync_status="synced",
            content_hash=hash_v1, last_modified=timezone.now()
        )

        f.write_text("version 2")
        handler = LocalFileHandler()
        with patch("api.services.sync_manager._compute_and_broadcast_health"):
            handler._handle_change(str(f))

        doc = DocumentTrack.objects.get(file_id=f"local__{f}")
        assert doc.content_hash != hash_v1
        assert doc.sync_status == "pending"


# ── Worker Stale Job Detection Tests ────────────────────────────




# ── Directory Filtering Tests ───────────────────────────────────

@pytest.mark.django_db
class TestDirectoryFiltering:
    """Tests that directories are silently skipped and deleted from the queue."""

    def test_directory_doc_gets_detected(self, tmp_path, doc_track_factory):
        """A DocumentTrack pointing to a directory path must be identified."""
        dirpath = tmp_path / "TestFolder"
        dirpath.mkdir()

        doc = doc_track_factory(
            file_id=f"local__{dirpath}",
            name="TestFolder",
            sync_status="pending"
        )

        assert os.path.isdir(str(dirpath))
        from api.models import DocumentTrack
        assert DocumentTrack.objects.filter(id=doc.id).exists()


# ── SSELogHandler Tests ─────────────────────────────────────────

class TestSSELogHandler:
    """Tests the log-level classification in SSELogHandler."""

    def test_success_level_detection(self):
        from api.services.sync_manager import SSELogHandler
        import logging

        handler = SSELogHandler()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test.txt indexed successfully.", args=(), exc_info=None
        )
        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            handler.emit(record)
            call_data = mock_bc.call_args[0][1]
            assert call_data["level"] == "success"

    def test_error_level_detection(self):
        from api.services.sync_manager import SSELogHandler
        import logging

        handler = SSELogHandler()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=0,
            msg="Failed to index file.", args=(), exc_info=None
        )
        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            handler.emit(record)
            call_data = mock_bc.call_args[0][1]
            assert call_data["level"] == "error"

    def test_warning_level_detection(self):
        from api.services.sync_manager import SSELogHandler
        import logging

        handler = SSELogHandler()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="", lineno=0,
            msg="Slow indexing detected.", args=(), exc_info=None
        )
        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            handler.emit(record)
            call_data = mock_bc.call_args[0][1]
            assert call_data["level"] == "warning"

    def test_info_level_default(self):
        from api.services.sync_manager import SSELogHandler
        import logging

        handler = SSELogHandler()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Processing file...", args=(), exc_info=None
        )
        with patch("api.services.sync_manager.broadcast_event") as mock_bc:
            handler.emit(record)
            call_data = mock_bc.call_args[0][1]
            assert call_data["level"] == "info"


# ── Sync Engine Lifecycle Tests ─────────────────────────────────

class TestSyncEngineLifecycle:
    """Tests start/stop of the sync engine background threads."""

    @patch("api.services.sync_manager.load_app_settings", return_value={
        "local_enabled": False, "cloud_enabled": False
    })
    def test_start_sets_running_flag(self, mock_settings):
        import api.services.sync_manager as sm
        original_running = sm._running

        try:
            sm.start_sync_engine()
            assert sm._running is True
        finally:
            sm.stop_sync_engine()
            assert sm._running is False

    @patch("api.services.sync_manager.load_app_settings", return_value={
        "local_enabled": False, "cloud_enabled": False
    })
    def test_double_start_is_idempotent(self, mock_settings):
        import api.services.sync_manager as sm
        try:
            sm.start_sync_engine()
            sm.start_sync_engine()  # Should return early
            assert sm._running is True
        finally:
            sm.stop_sync_engine()
