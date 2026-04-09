import pytest
from unittest.mock import MagicMock
from api.services.rag.generation.prompts import QA_PROMPT
from api.services.rag.generation.engine import build_query_engine

def test_strict_citation_prompt_format():
    """
    Validates that the QA prompt enforces strict context-only answering
    and mandatory citations.
    """
    template_str = QA_PROMPT.template
    
    assert "using ONLY the provided context" in template_str
    assert "I could not find relevant information" in template_str
    assert "Strictly cite" in template_str
    assert "[Source:" in template_str

from llama_index.core.query_engine import RetrieverQueryEngine

def test_build_query_engine(mock_llm):
    """
    Validates the engine dynamically glues the multi-retriever, LLM, and prompt together.
    """
    mock_merging_retriever = MagicMock()
    mock_rerank = MagicMock()
    
    engine = build_query_engine(mock_merging_retriever, mock_rerank)
    
    assert isinstance(engine, RetrieverQueryEngine)
