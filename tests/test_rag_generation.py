import pytest
from unittest.mock import MagicMock
from api.services.rag.generation.prompts import QA_PROMPT
from api.services.rag.generation.engine import build_query_engine, should_use_rag, extract_citations

def test_unified_prompt_format():
    """
    Validates that the hardened QA prompt enforces context usage,
    conciseness, and section-aware citations.
    """
    template_str = QA_PROMPT.template
    
    assert "PAIKS" in template_str
    assert "DOCUMENT EXCERPTS" in template_str
    assert "[Source:" in template_str
    assert "CONCISE" in template_str
    assert "NEVER say" in template_str
    assert "{context_str}" in template_str
    assert "{query_str}" in template_str

from llama_index.core.query_engine import RetrieverQueryEngine

def test_build_query_engine(mock_llm):
    """
    Validates the engine dynamically glues the multi-retriever, LLM, and prompt together.
    """
    mock_merging_retriever = MagicMock()
    mock_rerank = MagicMock()
    
    engine = build_query_engine(mock_merging_retriever, mock_rerank)
    
    assert isinstance(engine, RetrieverQueryEngine)

def test_should_use_rag_passes_with_high_score():
    """Tests that the similarity gate passes when scores are above threshold."""
    mock_node = MagicMock()
    mock_node.score = 0.75
    assert should_use_rag([mock_node]) is True

def test_should_use_rag_fails_with_low_score():
    """Tests that the similarity gate blocks when scores are below threshold."""
    mock_node = MagicMock()
    mock_node.score = 0.10
    assert should_use_rag([mock_node]) is False

def test_should_use_rag_fails_with_empty():
    """Tests that the similarity gate blocks when no results exist."""
    assert should_use_rag([]) is False

def test_extract_citations_with_section():
    """Tests parsing of [Source: filename → section] format."""
    text = "The system uses Django [Source: PAIKS Project.docx → Architecture]. It also has auth [Source: Config.txt → Setup]."
    _, citations = extract_citations(text)
    assert len(citations) == 2
    assert citations[0]["filename"] == "PAIKS Project.docx"
    assert citations[0]["section"] == "Architecture"
    assert citations[1]["filename"] == "Config.txt"
    assert citations[1]["section"] == "Setup"

def test_extract_citations_without_section():
    """Tests parsing of [Source: filename] format (no section)."""
    text = "The answer is here [Source: readme.md]."
    _, citations = extract_citations(text)
    assert len(citations) == 1
    assert citations[0]["filename"] == "readme.md"
    assert citations[0]["section"] == ""
