"""
Tests for api.services.rag.retrieval — Hybrid retriever and query rewriter.

Covers:
  - Base retriever initialization with VectorStoreIndex
  - AutoMergingRetriever wrapper construction
  - Query rewriting with LLM fallback
  - Filename detection (exact, partial, no match, ambiguous)
"""
import pytest
from unittest.mock import MagicMock
from llama_index.core import VectorStoreIndex
from api.services.rag.retrieval.hybrid import get_base_retriever, get_hybrid_merging_retriever
from api.services.rag.retrieval.query_rewriter import (
    rewrite_query, detect_filename_query,
)


class TestBaseRetriever:
    """Validates VectorIndexRetriever initialization."""

    def test_initialization(self):
        mock_index = MagicMock(spec=VectorStoreIndex)
        mock_index._embed_model = MagicMock()

        retriever = get_base_retriever(mock_index, top_k=5)
        assert retriever is not None
        assert getattr(retriever, '_similarity_top_k', None) == 5

    def test_default_top_k(self):
        mock_index = MagicMock(spec=VectorStoreIndex)
        mock_index._embed_model = MagicMock()

        retriever = get_base_retriever(mock_index)
        assert getattr(retriever, '_similarity_top_k', None) == 30


class TestAutoMergingRetriever:
    """Validates the hierarchical AutoMergingRetriever wrapper."""

    def test_initialization(self):
        mock_base = MagicMock()
        mock_storage = MagicMock()

        merger = get_hybrid_merging_retriever(mock_base, mock_storage)
        assert merger is not None
        assert merger._vector_retriever == mock_base


class TestFilenameDetection:
    """Validates filename detection in user queries."""

    def test_exact_match(self):
        known = [
            {"file_id": "f1", "file_name": "PAIKS Project.docx", "source": "local", "collection": "paiks_local_index"},
            {"file_id": "f2", "file_name": "Config Guide.pdf", "source": "cloud", "collection": "paiks_cloud_index"},
        ]
        result = detect_filename_query("Summarize the PAIKS Project file", known)
        assert result is not None
        assert result["file_id"] == "f1"

    def test_partial_match(self):
        known = [
            {"file_id": "f1", "file_name": "PAIKS Project.docx", "source": "local", "collection": "paiks_local_index"},
        ]
        result = detect_filename_query("what does paiks project say about auth?", known)
        assert result is not None
        assert result["file_id"] == "f1"

    def test_no_match(self):
        known = [
            {"file_id": "f1", "file_name": "PAIKS Project.docx", "source": "local", "collection": "paiks_local_index"},
        ]
        result = detect_filename_query("How does authentication work?", known)
        assert result is None

    def test_case_insensitive_match(self):
        known = [
            {"file_id": "f1", "file_name": "Research Paper.pdf", "source": "local", "collection": "paiks_local_index"},
        ]
        result = detect_filename_query("tell me about research paper", known)
        assert result is not None
        assert result["file_id"] == "f1"

    def test_longest_match_wins(self):
        """When multiple files match, the longest match should win."""
        known = [
            {"file_id": "f1", "file_name": "AI.txt", "source": "local", "collection": "paiks_local_index"},
            {"file_id": "f2", "file_name": "AI Research Paper.docx", "source": "local", "collection": "paiks_local_index"},
        ]
        result = detect_filename_query("What does AI Research Paper say?", known)
        assert result is not None
        assert result["file_id"] == "f2"

    def test_empty_known_files(self):
        result = detect_filename_query("Summarize everything", [])
        assert result is None

    def test_empty_file_name_skipped(self):
        known = [{"file_id": "f1", "file_name": "", "source": "local", "collection": "paiks_local_index"}]
        result = detect_filename_query("test query", known)
        assert result is None


class TestQueryRewriter:
    """Validates query rewriting with LLM."""

    def test_fallback_on_llm_failure(self, mock_llm):
        mock_llm.complete.side_effect = Exception("LLM offline")
        result = rewrite_query("How does auth work?")
        assert result == "How does auth work?"

    def test_successful_rewrite(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(
            __str__=lambda s: "authentication OAuth security"
        )
        result = rewrite_query("How does auth work?")
        assert result == "authentication OAuth security"

    def test_rewrite_with_history(self, mock_llm):
        mock_llm.complete.return_value = MagicMock(
            __str__=lambda s: "PAIKS Django authentication"
        )
        history = [
            {"role": "user", "content": "What is PAIKS?"},
            {"role": "assistant", "content": "A knowledge system."},
        ]
        result = rewrite_query("How does auth work?", history=history)
        assert result == "PAIKS Django authentication"

    def test_rewrite_too_long_falls_back(self, mock_llm):
        """If LLM returns absurdly long output, fall back to original."""
        mock_llm.complete.return_value = MagicMock(
            __str__=lambda s: "x" * 600  # Over 500 char limit
        )
        result = rewrite_query("simple query")
        assert result == "simple query"

    def test_rewrite_multiline_falls_back(self, mock_llm):
        """If LLM returns multi-line output, fall back to original."""
        mock_llm.complete.return_value = MagicMock(
            __str__=lambda s: "line one\nline two"
        )
        result = rewrite_query("simple query")
        assert result == "simple query"
