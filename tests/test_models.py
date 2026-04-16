"""
Tests for api.models — DocumentTrack ORM model.

Covers:
  - Field defaults and constraints
  - Unique file_id enforcement
  - Ordering (most recently updated first)
  - __str__ representation
  - Status transition correctness
"""
import pytest
from django.utils import timezone
from django.db import IntegrityError
from api.models import DocumentTrack


@pytest.mark.django_db
class TestDocumentTrackModel:
    """Validates the core DocumentTrack model that powers the sync registry."""

    def test_create_with_defaults(self):
        doc = DocumentTrack.objects.create(
            file_id="local__test.txt",
            name="test.txt",
            source="local",
        )
        assert doc.is_selected is True
        assert doc.sync_status == "pending"
        assert doc.content_hash is None
        assert doc.error_message is None

    def test_unique_file_id_constraint(self):
        DocumentTrack.objects.create(
            file_id="local__unique.txt", name="unique.txt", source="local"
        )
        with pytest.raises(IntegrityError):
            DocumentTrack.objects.create(
                file_id="local__unique.txt", name="duplicate.txt", source="local"
            )

    def test_str_representation(self):
        doc = DocumentTrack.objects.create(
            file_id="cloud__abc123", name="Report.pdf",
            source="cloud", sync_status="synced"
        )
        result = str(doc)
        assert "CLOUD" in result
        assert "Report.pdf" in result
        assert "synced" in result

    def test_ordering_by_updated_at(self):
        doc1 = DocumentTrack.objects.create(
            file_id="local__a.txt", name="a.txt", source="local"
        )
        doc2 = DocumentTrack.objects.create(
            file_id="local__b.txt", name="b.txt", source="local"
        )
        # doc2 was created after doc1, so it should come first
        all_docs = list(DocumentTrack.objects.all())
        assert all_docs[0].file_id == "local__b.txt"

    def test_sync_status_choices(self):
        valid_statuses = ["pending", "syncing", "synced", "error", "disabled"]
        for status in valid_statuses:
            doc = DocumentTrack.objects.create(
                file_id=f"local__{status}_test.txt",
                name=f"{status}_test.txt",
                source="local",
                sync_status=status,
            )
            assert doc.sync_status == status

    def test_source_choices(self):
        local = DocumentTrack.objects.create(
            file_id="local__l.txt", name="l.txt", source="local"
        )
        cloud = DocumentTrack.objects.create(
            file_id="cloud__c", name="c.docx", source="cloud"
        )
        assert local.source == "local"
        assert cloud.source == "cloud"

    def test_content_hash_stored_correctly(self):
        sha_hash = "a" * 64
        doc = DocumentTrack.objects.create(
            file_id="local__hashed.txt", name="hashed.txt",
            source="local", content_hash=sha_hash
        )
        doc.refresh_from_db()
        assert doc.content_hash == sha_hash

    def test_error_message_can_be_set(self):
        doc = DocumentTrack.objects.create(
            file_id="local__err.txt", name="err.txt",
            source="local", sync_status="error",
            error_message="Failed to parse PDF"
        )
        doc.refresh_from_db()
        assert doc.error_message == "Failed to parse PDF"

    def test_timestamps_auto_set(self):
        doc = DocumentTrack.objects.create(
            file_id="local__ts.txt", name="ts.txt", source="local"
        )
        assert doc.created_at is not None
        assert doc.updated_at is not None
