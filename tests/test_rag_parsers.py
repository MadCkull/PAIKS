import pytest
from unittest.mock import patch
from api.services.rag.ingestion.parsers import parse_cloud_file, parse_local_file

@patch("api.services.rag.ingestion.parsers.extract_text_from_drive")
def test_parse_cloud_file_success(mock_extract):
    # Setup mock to simulate a realistic extraction
    mock_extract.return_value = "This is a strictly mocked document extracted from google drive."
    
    file_info = {
        "id": "gd_123",
        "name": "Test Document.docx",
        "mime": "application/vnd.google-apps.document",
        "link": "https://docs.google.com/test",
        "modified": "2026-04-04T12:00:00Z"
    }

    doc = parse_cloud_file("mocked_service", file_info)
    
    # Assert LlamaIndex Document created correctly
    assert doc is not None
    assert doc.text == "This is a strictly mocked document extracted from google drive."
    
    # Assert Strict Metadata exists for citations
    assert doc.metadata["file_name"] == "Test Document.docx"
    assert doc.metadata["web_view_link"] == "https://docs.google.com/test"
    assert doc.metadata["source"] == "cloud"
    
    # Assert LLM invisible metadata limits tokens
    assert "web_view_link" in doc.excluded_llm_metadata_keys

@patch("api.services.rag.ingestion.parsers.extract_text_from_drive")
def test_parse_cloud_file_empty(mock_extract):
    # Simulate an empty pdf or blank document
    mock_extract.return_value = "   \n  "
    doc = parse_cloud_file("mocked_service", {"id": "1"})
    assert doc is None

@patch("api.services.rag.ingestion.parsers.pathlib.Path")
@patch("api.services.rag.ingestion.parsers.extract_text_from_local")
def test_parse_local_file_success(mock_extract, mock_path):
    # Setup completely faked local path to prevent touching real drives
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
