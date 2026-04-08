import pytest
from unittest.mock import MagicMock
from qdrant_client import QdrantClient

@pytest.fixture(autouse=True)
def mock_qdrant(mocker):
    """
    Automatically mock the QdrantClient everywhere in tests.
    It forces the indexer.py to use an ephemeral memory map (:memory:)
    so tests run instantly and do not corrupt the real .storage/qdrant_db.
    """
    mem_client = QdrantClient(location=":memory:")
    mocker.patch("api.services.rag.indexer.get_qdrant_client", return_value=mem_client)
    return mem_client

@pytest.fixture
def mock_llm(mocker):
    """
    Mock the Ollama LLM to return standard strings instead of requiring the GPU to spin up.
    """
    mock_engine = MagicMock()
    # Support for RAG query engine
    mock_engine.query.return_value = MagicMock(
        response="This is a mocked RAG response.",
        source_nodes=[]
    )
    # Support for Deterministic Router completion
    mock_engine.complete.return_value = MagicMock(
        __str__=lambda s: "SEARCH" # Default to SEARCH for safety
    )
    mocker.patch("api.services.rag.generation.engine.get_llm", return_value=mock_engine)
    return mock_engine
