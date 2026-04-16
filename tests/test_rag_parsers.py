"""
Tests for api.services.rag.ingestion.parsers — Document parsing with junk detection.

Covers:
  - is_text_junk heuristic (alphanumeric ratio, repetition, short text)
  - parse_cloud_file with proper metadata
  - parse_local_file with proper metadata
  - Edge cases: empty, junk, exception handling
"""
import pytest
from unittest.mock import patch, MagicMock
from api.services.rag.ingestion.parsers import (
    parse_cloud_file, parse_local_file, is_text_junk
)


class TestIsTextJunk:
    """Validates the junk-detection heuristic that protects against garbage ingestion."""

    def test_none_is_junk(self):
        assert is_text_junk(None) is True

    def test_empty_is_junk(self):
        assert is_text_junk("") is True

    def test_short_is_junk(self):
        assert is_text_junk("hello") is True

    def test_whitespace_only_is_junk(self):
        assert is_text_junk("   \n  ") is True

    def test_normal_text_is_not_junk(self):
        assert is_text_junk("This is a perfectly normal document about machine learning.") is False

    def test_binary_noise_is_junk(self):
        binary_garbage = "".join(chr(i) for i in range(1, 50)) * 10
        assert is_text_junk(binary_garbage) is True

    def test_extreme_repetition_is_junk(self):
        repeated = "x" * 500
        assert is_text_junk(repeated) is True

    def test_mixed_content_not_junk(self):
        mixed = "Chapter 1: Introduction\n\nThis paper discusses the design of RAG systems." * 5
        assert is_text_junk(mixed) is False


class TestParseCloudFile:
    """Validates cloud file parsing into LlamaIndex Documents."""

    @patch("api.services.rag.ingestion.parsers.extract_text_from_drive")
    def test_success_with_full_metadata(self, mock_extract):
        mock_extract.return_value = "This is a strictly mocked document extracted from google drive."

        file_info = {
            "id": "gd_123",
            "name": "Test Document.docx",
            "mime": "application/vnd.google-apps.document",
            "link": "https://docs.google.com/test",
            "modified": "2026-04-04T12:00:00Z"
        }

        doc = parse_cloud_file("mocked_service", file_info)

        assert doc is not None
        assert doc.text == "This is a strictly mocked document extracted from google drive."
        assert doc.metadata["file_name"] == "Test Document.docx"
        assert doc.metadata["web_view_link"] == "https://docs.google.com/test"
        assert doc.metadata["source"] == "cloud"
        assert doc.metadata["is_summary"] is False
        assert "web_view_link" in doc.excluded_llm_metadata_keys

    @patch("api.services.rag.ingestion.parsers.extract_text_from_drive")
    def test_empty_returns_none(self, mock_extract):
        mock_extract.return_value = "   \n  "
        doc = parse_cloud_file("mocked_service", {"id": "1"})
        assert doc is None

    @patch("api.services.rag.ingestion.parsers.extract_text_from_drive")
    def test_junk_returns_none(self, mock_extract):
        mock_extract.return_value = "\x00\x01\x02" * 100
        doc = parse_cloud_file("mocked_service", {"id": "j"})
        assert doc is None

    @patch("api.services.rag.ingestion.parsers.extract_text_from_drive")
    def test_exception_returns_none(self, mock_extract):
        mock_extract.side_effect = Exception("Network error")
        doc = parse_cloud_file("mocked_service", {"id": "err", "name": "broken.pdf"})
        assert doc is None


class TestParseLocalFile:
    """Validates local file parsing into LlamaIndex Documents."""

    @patch("api.services.rag.ingestion.parsers.pathlib.Path")
    @patch("api.services.rag.ingestion.parsers.extract_text_from_local")
    def test_success(self, mock_extract, mock_path):
        mock_path_instance = mock_path.return_value
        mock_path_instance.exists.return_value = True
        mock_extract.return_value = "Local file contents read from strictly mocked disk."

        file_info = {
            "id": "loc_456",
            "name": "Report.pdf",
            "local_path": "C:\\fake\\path\\Report.pdf"
        }
        doc = parse_local_file(file_info)

        assert doc is not None
        assert doc.metadata["file_name"] == "Report.pdf"
        assert doc.metadata["source"] == "local"
        assert "local_path" in doc.excluded_llm_metadata_keys

    @patch("api.services.rag.ingestion.parsers.pathlib.Path")
    def test_nonexistent_path_returns_none(self, mock_path):
        mock_path.return_value.exists.return_value = False
        doc = parse_local_file({"id": "x", "local_path": "C:\\fake\\missing.txt"})
        assert doc is None

    @patch("api.services.rag.ingestion.parsers.pathlib.Path")
    @patch("api.services.rag.ingestion.parsers.extract_text_from_local")
    def test_junk_content_returns_none(self, mock_extract, mock_path):
        mock_path.return_value.exists.return_value = True
        mock_extract.return_value = "\x00" * 200
        doc = parse_local_file({"id": "j", "name": "junk.bin", "local_path": "C:\\fake\\junk.bin"})
        assert doc is None
