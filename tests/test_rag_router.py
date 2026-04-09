import pytest
from unittest.mock import MagicMock
from api.services.rag.retrieval.query_rewriter import (
    rewrite_query, detect_filename_query,
)

def test_detect_filename_exact_match():
    """Ensures filename detection works for exact name matches."""
    known = [
        {"file_id": "f1", "file_name": "PAIKS Project.docx", "source": "local", "collection": "paiks_local_index"},
        {"file_id": "f2", "file_name": "Config Guide.pdf", "source": "cloud", "collection": "paiks_cloud_index"},
    ]
    
    result = detect_filename_query("Summarize the PAIKS Project file", known)
    assert result is not None
    assert result["file_id"] == "f1"

def test_detect_filename_partial_match():
    """Ensures filename detection works for partial name matches."""
    known = [
        {"file_id": "f1", "file_name": "PAIKS Project.docx", "source": "local", "collection": "paiks_local_index"},
    ]
    
    result = detect_filename_query("what does paiks project say about auth?", known)
    assert result is not None
    assert result["file_id"] == "f1"

def test_detect_filename_no_match():
    """Ensures no false positive when no filename is mentioned."""
    known = [
        {"file_id": "f1", "file_name": "PAIKS Project.docx", "source": "local", "collection": "paiks_local_index"},
    ]
    
    result = detect_filename_query("How does authentication work?", known)
    assert result is None

def test_rewrite_query_fallback(mock_llm):
    """Ensures query rewriter falls back to original on LLM failure."""
    mock_llm.complete.side_effect = Exception("LLM offline")
    result = rewrite_query("How does auth work?")
    assert result == "How does auth work?"
