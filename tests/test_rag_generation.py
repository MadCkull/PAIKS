"""
Tests for api.services.rag.generation — Engine, prompts, similarity gate, citations.

Covers:
  - Unified prompt template structure
  - build_query_engine assembly
  - should_use_rag similarity gate (pass/fail/empty)
  - extract_citations regex parsing
  - build_query_with_history formatting
"""
import pytest
from unittest.mock import MagicMock
from api.services.rag.generation.prompts import QA_PROMPT, build_query_with_history
from api.services.rag.generation.engine import (
    build_query_engine, should_use_rag, extract_citations
)
from llama_index.core.query_engine import RetrieverQueryEngine


class TestUnifiedPrompt:
    """Validates the QA prompt template structure."""

    def test_prompt_contains_required_elements(self):
        template_str = QA_PROMPT.template
        assert "PAIKS" in template_str
        assert "CONTEXT" in template_str
        assert "concise" in template_str.lower()
        assert "Never say" in template_str
        assert "{context_str}" in template_str
        assert "{query_str}" in template_str

    def test_prompt_has_conversation_history_rule(self):
        template_str = QA_PROMPT.template
        assert "conversation history" in template_str.lower()


class TestBuildQueryWithHistory:
    """Validates history injection into the query string."""

    def test_no_history(self):
        result = build_query_with_history("What is PAIKS?")
        assert result == "Question: What is PAIKS?"

    def test_with_history(self):
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "Tell me about auth."},
        ]
        result = build_query_with_history("How does it work?", history)
        assert "CONVERSATION HISTORY" in result
        assert "User: Hi" in result
        assert "Assistant: Hello!" in result
        assert "Question: How does it work?" in result

    def test_empty_history(self):
        result = build_query_with_history("Test query", [])
        assert result == "Question: Test query"

    def test_history_truncation_to_last_6(self):
        history = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        result = build_query_with_history("final", history)
        # Should only include last 6 messages
        assert "msg 4" in result
        assert "msg 9" in result
        # msg 0-3 should be excluded
        assert "msg 0" not in result


class TestBuildQueryEngine:
    """Validates engine assembly with mocked components."""

    def test_engine_construction(self, mock_llm):
        mock_retriever = MagicMock()
        mock_reranker = MagicMock()
        engine = build_query_engine(mock_retriever, mock_reranker)
        assert isinstance(engine, RetrieverQueryEngine)

    def test_engine_without_reranker(self, mock_llm):
        mock_retriever = MagicMock()
        engine = build_query_engine(mock_retriever, None)
        assert isinstance(engine, RetrieverQueryEngine)


class TestSimilarityGate:
    """Validates the should_use_rag score threshold logic."""

    def test_high_score_passes(self):
        node = MagicMock()
        node.score = 0.75
        assert should_use_rag([node]) is True

    def test_exact_threshold_passes(self):
        node = MagicMock()
        node.score = 0.30
        assert should_use_rag([node]) is True

    def test_below_threshold_fails(self):
        node = MagicMock()
        node.score = 0.10
        assert should_use_rag([node]) is False

    def test_empty_list_fails(self):
        assert should_use_rag([]) is False

    def test_multiple_nodes_uses_max(self):
        n1 = MagicMock()
        n1.score = 0.05
        n2 = MagicMock()
        n2.score = 0.50
        assert should_use_rag([n1, n2]) is True

    def test_none_scores_handled(self):
        n1 = MagicMock()
        n1.score = None
        assert should_use_rag([n1]) is False

    def test_custom_threshold(self):
        node = MagicMock()
        node.score = 0.40
        assert should_use_rag([node], threshold=0.50) is False
        assert should_use_rag([node], threshold=0.30) is True


class TestExtractCitations:
    """Validates citation parsing from LLM responses."""

    def test_with_section(self):
        text = "Uses Django [Source: PAIKS Project.docx → Architecture]. Auth via [Source: Config.txt → Setup]."
        _, citations = extract_citations(text)
        assert len(citations) == 2
        assert citations[0]["filename"] == "PAIKS Project.docx"
        assert citations[0]["section"] == "Architecture"
        assert citations[1]["filename"] == "Config.txt"
        assert citations[1]["section"] == "Setup"

    def test_without_section(self):
        text = "The answer is here [Source: readme.md]."
        _, citations = extract_citations(text)
        assert len(citations) == 1
        assert citations[0]["filename"] == "readme.md"
        assert citations[0]["section"] == ""

    def test_no_citations(self):
        text = "Just a plain response with no sources."
        _, citations = extract_citations(text)
        assert citations == []

    def test_duplicate_citations_deduplicated(self):
        text = ("[Source: doc.pdf → Intro] says A. "
                "[Source: doc.pdf → Intro] says B.")
        _, citations = extract_citations(text)
        assert len(citations) == 1

    def test_mixed_citations(self):
        text = ("[Source: file1.txt] and [Source: file2.pdf → Methods] "
                "and [Source: file3.docx → Results]")
        _, citations = extract_citations(text)
        assert len(citations) == 3
