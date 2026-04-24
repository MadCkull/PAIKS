"""
Tests for api.views.rag — RAG search endpoint and status endpoint.

Covers:
  - Status endpoint reads Qdrant collection counts
  - Search endpoint triggers full pipeline with mocked components
  - General intent handling (greetings)
  - MultiCollectionRetriever fan-out
  - Error handling for missing query
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from django.test import RequestFactory
from api.views.rag import search, status, MultiCollectionRetriever


@pytest.fixture
def api_rf():
    return RequestFactory()


@pytest.mark.django_db
@patch("api.services.rag.indexer.get_qdrant_client")
def test_rag_status_endpoint(mock_client, api_rf, doc_track_factory):
    """Validates the status endpoint correctly reads from the Qdrant DB."""
    doc_track_factory(file_id="local__test.txt", sync_status="synced")

    mock_q = MagicMock()
    mock_q.collection_exists.return_value = True
    coll_mock = MagicMock()
    coll_mock.points_count = 25
    mock_q.get_collection.return_value = coll_mock
    mock_client.return_value = mock_q

    req = api_rf.get('/api/rag/status')
    response = status(req)

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["indexed"] is True
    assert data["total_chunks"] == 1


@pytest.mark.django_db
@patch("api.services.rag.indexer.get_qdrant_client")
def test_rag_status_no_collections(mock_client, api_rf):
    """Status endpoint with no collections should return not indexed."""
    mock_q = MagicMock()
    mock_q.collection_exists.return_value = False
    mock_client.return_value = mock_q

    req = api_rf.get('/api/rag/status')
    response = status(req)

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["indexed"] is False
    assert data["total_chunks"] == 0


def test_search_missing_query(api_rf):
    """Search endpoint must return 400 for empty query."""
    req = api_rf.post(
        '/api/rag/search',
        data=json.dumps({"query": ""}),
        content_type="application/json"
    )
    response = search(req)
    assert response.status_code == 400


def test_search_no_body(api_rf):
    """Search endpoint with empty body should return 400."""
    req = api_rf.post('/api/rag/search', data=b"", content_type="application/json")
    response = search(req)
    assert response.status_code == 400


@patch("api.views.rag.build_query_engine")
@patch("api.services.rag.indexer.get_qdrant_client")
@patch("api.services.rag.retrieval.reranker.get_cross_encoder_reranker")
@patch("api.views.rag.VectorStoreIndex.from_vector_store")
@patch("api.views.rag.get_embedder")
@patch("api.services.rag.retrieval.query_rewriter.get_known_files_from_qdrant")
@patch("api.services.rag.retrieval.query_rewriter.detect_filename_query")
def test_rag_search_endpoint(
    mock_detect, mock_known,
    mock_embed, mock_vsi, mock_reranker, mock_client,
    mock_engine_builder, api_rf
):
    """Validates search triggers the full RAG pipeline and returns cited chunks."""
    mock_known.return_value = []
    mock_detect.return_value = None

    mock_q = MagicMock()
    mock_q.collection_exists.return_value = True
    mock_client.return_value = mock_q

    mock_engine = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = lambda s: "This is a generated answer. [Source: doc.pdf → Introduction]"

    mock_node = MagicMock()
    mock_node.score = 0.95
    mock_node.node.metadata = {
        "file_name": "doc.pdf",
        "file_id": "local__doc.pdf",
        "source": "local",
        "section_header": "Introduction",
    }
    mock_node.node.get_content.return_value = "Snippet of doc.pdf content."
    mock_response.source_nodes = [mock_node]

    mock_engine.retrieve.return_value = [mock_node]
    mock_engine.synthesize.return_value = mock_response
    mock_engine_builder.return_value = mock_engine

    req = api_rf.post(
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
@patch("api.services.rag.retrieval.query_rewriter.get_known_files_from_qdrant")
@patch("api.services.rag.retrieval.query_rewriter.detect_filename_query")
def test_rag_search_general_intent(
    mock_detect, mock_known,
    mock_embed, mock_vsi, mock_client,
    mock_engine_builder, api_rf
):
    """Validates that greetings work with the unified prompt."""
    mock_known.return_value = []
    mock_detect.return_value = None

    mock_q = MagicMock()
    mock_q.collection_exists.return_value = True
    mock_client.return_value = mock_q

    mock_engine = MagicMock()
    mock_response = MagicMock()
    mock_response.__str__ = lambda s: "Hello! How can I help you today?"
    mock_response.source_nodes = []

    mock_engine.retrieve.return_value = []
    mock_engine.synthesize.return_value = mock_response
    mock_engine_builder.return_value = mock_engine

    req = api_rf.post(
        '/api/rag/search',
        data=json.dumps({"query": "Hii"}),
        content_type="application/json"
    )
    response = search(req)

    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["answer"] == "Hello! How can I help you today?"
    assert data["source"] == "semantic_multi"


class TestMultiCollectionRetriever:
    """Validates the custom multi-collection retriever fan-out."""

    def test_both_retrievers_queried(self):
        cloud_ret = MagicMock()
        local_ret = MagicMock()

        cloud_node = MagicMock()
        local_node = MagicMock()
        cloud_ret.retrieve.return_value = [cloud_node]
        local_ret.retrieve.return_value = [local_node]

        mcr = MultiCollectionRetriever(cloud_ret, local_ret)
        from llama_index.core import QueryBundle
        results = mcr._retrieve(QueryBundle("test"))

        assert len(results) == 2
        cloud_ret.retrieve.assert_called_once()
        local_ret.retrieve.assert_called_once()

    def test_one_retriever_none(self):
        local_ret = MagicMock()
        local_ret.retrieve.return_value = [MagicMock()]

        mcr = MultiCollectionRetriever(None, local_ret)
        from llama_index.core import QueryBundle
        results = mcr._retrieve(QueryBundle("test"))

        assert len(results) == 1

    def test_both_retrievers_none(self):
        mcr = MultiCollectionRetriever(None, None)
        from llama_index.core import QueryBundle
        results = mcr._retrieve(QueryBundle("test"))
        assert results == []

    def test_retriever_exception_handled(self):
        """If one retriever fails, the other should still work."""
        cloud_ret = MagicMock()
        local_ret = MagicMock()

        cloud_ret.retrieve.side_effect = Exception("Cloud down")
        local_ret.retrieve.return_value = [MagicMock()]

        mcr = MultiCollectionRetriever(cloud_ret, local_ret)
        from llama_index.core import QueryBundle
        results = mcr._retrieve(QueryBundle("test"))

        assert len(results) == 1  # Only local results
