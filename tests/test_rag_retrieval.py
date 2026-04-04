import pytest
from unittest.mock import MagicMock
from llama_index.core import VectorStoreIndex, Document
from llama_index.core.storage.docstore import SimpleDocumentStore
from api.services.rag.retrieval.hybrid import get_base_retriever, get_hybrid_merging_retriever

def test_base_retriever_initialization():
    """
    Validates that our custom base hybrid retriever configures successfully 
    without failing on Qdrant args.
    """
    mock_index = MagicMock(spec=VectorStoreIndex)
    mock_index._embed_model = MagicMock()
    
    retriever = get_base_retriever(mock_index, top_k=5)
    
    assert retriever is not None
    assert getattr(retriever, '_similarity_top_k', None) == 5

def test_auto_merging_retriever_initialization():
    """
    Validates the complex Hierarchical AutoMerging retriever wrapper wraps correctly.
    """
    mock_base = MagicMock()
    mock_storage = MagicMock()
    
    merger = get_hybrid_merging_retriever(mock_base, mock_storage)
    assert merger is not None
    assert merger._vector_retriever == mock_base
