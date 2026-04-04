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
    mock_engine.query.return_value = MagicMock(
        response="This is a mocked LLM response.",
        source_nodes=[]
    )
    mocker.patch("api.services.rag.generation.engine.get_llm", return_value=mock_engine)
    return mock_engine
