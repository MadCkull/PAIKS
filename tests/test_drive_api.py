"""
Tests for api.views.drive — Selection endpoint, selections query, and stats.

Covers:
  - File selection/deselection with queue effects
  - Bulk selection processing
  - Health broadcast triggers
  - Selections query (selected/disabled/error/synced maps)
  - Stats endpoint with mixed document states
  - Invalid JSON error handling
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from django.utils import timezone


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def doc_factory(db):
    from api.models import DocumentTrack

    def _create(file_id, name=None, source="local", is_selected=True,
                sync_status="synced", content_hash="h"):
        return DocumentTrack.objects.create(
            file_id=file_id,
            name=name or file_id.split("__")[-1],
            source=source,
            is_selected=is_selected,
            sync_status=sync_status,
            content_hash=content_hash,
            last_modified=timezone.now()
        )
    return _create


# ── Selection Endpoint Tests ────────────────────────────────────

@pytest.mark.django_db
class TestSelectionEndpoint:
    """Tests POST /api/drive/selection — the core file selection toggle."""

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_select_file_creates_doc_and_queues(self, mock_health, mock_q, rf):
        from api.views.drive import selection

        body = json.dumps({
            "file_ids": ["local__D:\\test\\file.txt"],
            "is_selected": True
        })
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        resp = selection(req)

        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data["status"] == "updated"
        assert data["count"] == 1

        from api.models import DocumentTrack
        doc = DocumentTrack.objects.get(file_id="local__D:\\test\\file.txt")
        assert doc.is_selected is True
        assert doc.sync_status == "pending"

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_deselect_file_marks_disabled(self, mock_health, mock_q, rf, doc_factory):
        from api.views.drive import selection

        doc_factory("local__D:\\test\\a.txt", sync_status="synced")

        body = json.dumps({
            "file_ids": ["local__D:\\test\\a.txt"],
            "is_selected": False
        })
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        resp = selection(req)

        assert resp.status_code == 200

        from api.models import DocumentTrack
        doc = DocumentTrack.objects.get(file_id="local__D:\\test\\a.txt")
        assert doc.is_selected is False
        assert doc.sync_status == "disabled"

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_deselect_triggers_health_broadcast(self, mock_health, mock_q, rf, doc_factory):
        from api.views.drive import selection

        doc_factory("local__x.txt")

        body = json.dumps({"file_ids": ["local__x.txt"], "is_selected": False})
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        selection(req)

        mock_health.assert_called_once()

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_select_triggers_index_queue(self, mock_health, mock_q, rf):
        from api.views.drive import selection

        body = json.dumps({
            "file_ids": ["local__D:\\data\\report.pdf"],
            "is_selected": True
        })
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        selection(req)

        mock_q.put.assert_called_once()
        call_args = mock_q.put.call_args[0][0]
        assert call_args["action"] == "index"

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_deselect_triggers_delete_queue(self, mock_health, mock_q, rf, doc_factory):
        from api.views.drive import selection

        doc_factory("local__D:\\data\\old.txt")

        body = json.dumps({
            "file_ids": ["local__D:\\data\\old.txt"],
            "is_selected": False
        })
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        selection(req)

        mock_q.put.assert_called_once()
        call_args = mock_q.put.call_args[0][0]
        assert call_args["action"] == "delete"
        assert call_args["file_id"] == "local__D:\\data\\old.txt"

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_bulk_selection(self, mock_health, mock_q, rf):
        """Selecting multiple files in one request must process all."""
        from api.views.drive import selection

        body = json.dumps({
            "file_ids": ["local__a.txt", "local__b.txt", "local__c.txt"],
            "is_selected": True
        })
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        resp = selection(req)

        data = json.loads(resp.content)
        assert data["count"] == 3
        assert mock_q.put.call_count == 3

    def test_invalid_json_returns_400(self, rf):
        from api.views.drive import selection

        req = rf.post("/api/drive/selection", data="not json", content_type="application/json")
        resp = selection(req)
        assert resp.status_code == 400

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_reselect_errored_file_resets_to_pending(self, mock_health, mock_q, rf, doc_factory):
        """Re-selecting a file that previously errored must reset its status."""
        from api.views.drive import selection

        doc_factory("local__broken.pdf", sync_status="error")

        body = json.dumps({"file_ids": ["local__broken.pdf"], "is_selected": True})
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        selection(req)

        from api.models import DocumentTrack
        doc = DocumentTrack.objects.get(file_id="local__broken.pdf")
        assert doc.sync_status == "pending"
        assert doc.is_selected is True

    @patch("api.services.sync_manager._index_queue")
    @patch("api.services.sync_manager._compute_and_broadcast_health")
    def test_cloud_file_detection(self, mock_health, mock_q, rf):
        """Cloud file IDs must be detected and stored with source='cloud'."""
        from api.views.drive import selection

        body = json.dumps({
            "file_ids": ["cloud__abc123def"],
            "is_selected": True
        })
        req = rf.post("/api/drive/selection", data=body, content_type="application/json")
        selection(req)

        from api.models import DocumentTrack
        doc = DocumentTrack.objects.get(file_id="cloud__abc123def")
        assert doc.source == "cloud"


# ── Selections Query Tests ──────────────────────────────────────

@pytest.mark.django_db
class TestSelectionsQuery:
    """Tests GET /api/drive/selections — returns file state maps."""

    def test_returns_selected_and_disabled(self, rf, doc_factory):
        from api.views.drive import selections

        doc_factory("local__a.txt", is_selected=True)
        doc_factory("local__b.txt", is_selected=False)

        req = rf.get("/api/drive/selections")
        resp = selections(req)
        data = json.loads(resp.content)

        assert "local__a.txt" in data["selected"]
        assert "local__b.txt" in data["disabled"]

    def test_returns_error_ids(self, rf, doc_factory):
        from api.views.drive import selections

        doc_factory("local__bad.pdf", sync_status="error")

        req = rf.get("/api/drive/selections")
        resp = selections(req)
        data = json.loads(resp.content)

        assert "local__bad.pdf" in data["errors"]

    def test_returns_synced_ids(self, rf, doc_factory):
        from api.views.drive import selections

        doc_factory("local__good.txt", sync_status="synced", is_selected=True)

        req = rf.get("/api/drive/selections")
        resp = selections(req)
        data = json.loads(resp.content)

        assert "local__good.txt" in data["synced"]

    def test_deselected_synced_not_in_synced_list(self, rf, doc_factory):
        """synced list only includes selected+synced files."""
        from api.views.drive import selections

        doc_factory("local__old.txt", sync_status="synced", is_selected=False)

        req = rf.get("/api/drive/selections")
        resp = selections(req)
        data = json.loads(resp.content)

        assert "local__old.txt" not in data["synced"]

    def test_empty_db_returns_empty_lists(self, rf, db):
        from api.views.drive import selections

        req = rf.get("/api/drive/selections")
        resp = selections(req)
        data = json.loads(resp.content)

        assert data["selected"] == []
        assert data["disabled"] == []
        assert data["errors"] == []
        assert data["synced"] == []


# ── Stats Endpoint Tests ───────────────────────────────────────

@pytest.mark.django_db
class TestStatsEndpoint:
    """Tests GET /api/drive/stats — real-time system metrics."""

    @patch("api.views.drive.get_creds", return_value=None)
    @patch("api.views.drive.load_app_settings", return_value={})
    def test_stats_returns_correct_counts(self, mock_settings, mock_creds, rf, doc_factory):
        from api.views.drive import stats

        doc_factory("local__a.txt", sync_status="synced")
        doc_factory("local__b.txt", sync_status="error")
        doc_factory("cloud__c", source="cloud", sync_status="synced")
        doc_factory("local__d.txt", sync_status="disabled", is_selected=False)

        req = rf.get("/api/drive/stats")
        resp = stats(req)
        data = json.loads(resp.content)

        assert data["indexed_total"] == 2   # a.txt + cloud__c
        assert data["error_total"] == 1     # b.txt
        assert data["disabled_total"] == 1  # d.txt
        assert data["local_total"] == 3     # a, b, d
        assert data["cloud_total"] == 1     # c

    @patch("api.views.drive.get_creds", return_value=None)
    @patch("api.views.drive.load_app_settings", return_value={})
    def test_stats_empty_db(self, mock_settings, mock_creds, rf):
        from api.views.drive import stats

        req = rf.get("/api/drive/stats")
        resp = stats(req)
        data = json.loads(resp.content)

        assert data["indexed_total"] == 0
        assert data["documents_total"] == 0
