import pytest
import json
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.test import RequestFactory
from api.views.rag import search, status

@pytest.fixture
def api_request_factory():
    return RequestFactory()

@patch("api.services.rag.indexer.get_qdrant_client")
def test_rag_status_endpoint(mock_client, api_request_factory):
    """
    Validates the status endpoint correctly reads from the Qdrant DB.
    """
    # Mock local/cloud collections having 50 chunks combined
    mock_q = MagicMock()
    mock_q.collection_exists.return_value = True
    coll_mock = MagicMock()
    coll_mock.points_count = 25
    mock_q.get_collection.return_value = coll_mock
    mock_client.return_value = mock_q
    
    req = api_request_factory.get('/api/rag/status')
    response = status(req)
    
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["indexed"] is True
    assert data["total_chunks"] == 50

@patch("api.views.rag.build_query_engine")
@patch("api.services.rag.indexer.get_qdrant_client")
@patch("api.services.rag.retrieval.reranker.get_cross_encoder_reranker")
@patch("api.views.rag.VectorStoreIndex.from_vector_store")
@patch("api.views.rag.get_embedder")
@patch("api.services.rag.retrieval.query_rewriter.rewrite_query")
@patch("api.services.rag.retrieval.query_rewriter.get_known_files_from_qdrant")
@patch("api.services.rag.retrieval.query_rewriter.detect_filename_query")
def test_rag_search_endpoint(
    mock_detect, mock_known, mock_rewrite,
    mock_embed, mock_vsi, mock_reranker, mock_client,
    mock_engine_builder, api_request_factory
):
    """
    Validates that queries trigger the full RAG pipeline (no routing)
    and return cited chunks with the rewritten query.
    """
    # Query intelligence mocks
    mock_known.return_value = []
    mock_detect.return_value = None
    mock_rewrite.return_value = "test document query optimized"
    
    mock_q = MagicMock()
    mock_q.collection_exists.return_value = True
    mock_client.return_value = mock_q
    
    # Mock LLM String Response
    mock_engine = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__.return_value = "This is a generated answer. [Source: doc.pdf → Introduction]"
    
    # Mock the retrieved nodes
    mock_node = MagicMock()
    mock_node.score = 0.95
    mock_node.node.metadata = {
        "file_name": "doc.pdf",
        "source": "local",
        "section_header": "Introduction",
    }
    mock_node.node.get_content.return_value = "Snippet of doc.pdf content."
    mock_response.source_nodes = [mock_node]
    
    mock_engine.retrieve.return_value = [mock_node]
    mock_engine.synthesize.return_value = mock_response
    mock_engine_builder.return_value = mock_engine
    
    req = api_request_factory.post(
        '/api/rag/search',
        data=json.dumps({"query": "Test Document Query"}),
        content_type="application/json"
    )
    response = search(req)
    
    assert response.status_code == 200
    data = json.loads(response.content)
    
    assert data["answer_error"] is None
    assert "[Source: doc.pdf" in data["answer"]
    assert data["source"] == "semantic_multi"
    assert len(data["results"]) == 1
    assert data["results"][0]["section"] == "Introduction"

@patch("api.views.rag.build_query_engine")
@patch("api.services.rag.indexer.get_qdrant_client")
@patch("api.views.rag.VectorStoreIndex.from_vector_store")
@patch("api.views.rag.get_embedder")
@patch("api.services.rag.retrieval.query_rewriter.rewrite_query")
@patch("api.services.rag.retrieval.query_rewriter.get_known_files_from_qdrant")
@patch("api.services.rag.retrieval.query_rewriter.detect_filename_query")
def test_rag_search_general_intent(
    mock_detect, mock_known, mock_rewrite,
    mock_embed, mock_vsi, mock_client,
    mock_engine_builder, api_request_factory
):
    """
    Validates that greetings still work — the unified prompt handles
    general responses when no relevant context is found.
    """
    mock_known.return_value = []
    mock_detect.return_value = None
    mock_rewrite.return_value = "hi greeting"
    
    mock_q = MagicMock()
    mock_q.collection_exists.return_value = True
    mock_client.return_value = mock_q
    
    mock_engine = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__.return_value = "Hello! How can I help you today?"
    mock_response.source_nodes = []
    
    mock_engine.retrieve.return_value = []
    mock_engine.synthesize.return_value = mock_response
    mock_engine_builder.return_value = mock_engine
    
    req = api_request_factory.post(
        '/api/rag/search',
        data=json.dumps({"query": "Hii"}),
        content_type="application/json"
    )
    response = search(req)
    
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["answer"] == "Hello! How can I help you today?"
    assert data["source"] == "semantic_multi"
