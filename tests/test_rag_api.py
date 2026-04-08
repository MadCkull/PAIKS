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

@patch("api.views.rag.classify_intent")
@patch("api.views.rag.get_general_response")
def test_rag_search_general_intent(mock_general_resp, mock_classify, api_request_factory):
    """
    Validates that if the intent classifier returns GENERAL,
    the RAG retrieval is bypassed and a simple chat response is returned.
    """
    mock_classify.return_value = "GENERAL"
    mock_general_resp.return_value = "Hello! Warm greeting."
    
    req = api_request_factory.post('/api/rag/search', data=json.dumps({"query": "Hii"}), content_type="application/json")
    response = search(req)
    
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["answer"] == "Hello! Warm greeting."
    assert data["source"] == "conversational"
    assert len(data["results"]) == 0

@patch("api.views.rag.classify_intent")
@patch("api.views.rag.build_query_engine")
@patch("api.services.rag.indexer.get_qdrant_client")
@patch("api.services.rag.retrieval.reranker.get_cross_encoder_reranker")
@patch("api.views.rag.VectorStoreIndex.from_vector_store")
@patch("api.views.rag.get_embedder")
def test_rag_search_endpoint(mock_embed, mock_vsi, mock_reranker, mock_client, mock_engine_builder, mock_classify, api_request_factory):
    """
    Validates that technical queries trigger the full RAG pipeline and return cited chunks.
    """
    mock_classify.return_value = "SEARCH"
    mock_q = MagicMock()
    mock_q.collection_exists.return_value = True
    mock_client.return_value = mock_q
    
    # Mock LLM String Response
    mock_engine = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__.return_value = "This is a strictly generated answer. [Source: doc.pdf]"
    
    # Mock the retrieved nodes
    mock_node = MagicMock()
    mock_node.score = 0.95
    mock_node.node.metadata = {"file_name": "doc.pdf", "source": "local"}
    mock_node.node.get_content.return_value = "Snippet of doc.pdf content."
    mock_response.source_nodes = [mock_node]
    
    mock_engine.query.return_value = mock_response
    mock_engine_builder.return_value = mock_engine
    
    req = api_request_factory.post('/api/rag/search', data=json.dumps({"query": "Test Document Query"}), content_type="application/json")
    response = search(req)
    
    assert response.status_code == 200
    data = json.loads(response.content)
    
    assert data["answer_error"] is None
    assert data["answer"] == "This is a strictly generated answer. [Source: doc.pdf]"
    assert data["source"] == "semantic_multi"
    assert len(data["results"]) == 1
