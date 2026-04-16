"""
Shared pytest fixtures for the PAIKS test suite.

Provides:
  - mock_qdrant   : auto-used in-memory Qdrant client (prevents disk I/O)
  - mock_llm      : mocked Ollama LLM (prevents GPU / network dependency)
  - tmp_storage   : ephemeral STORAGE_DIR for config tests
  - doc_track_factory : helper to create DocumentTrack rows quickly
"""
import pytest
import queue
from unittest.mock import MagicMock
from qdrant_client import QdrantClient


# ── Qdrant In-Memory Client ────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_qdrant(mocker):
    """
    Automatically mock the QdrantClient everywhere in tests.
    Forces indexer.py to use an ephemeral in-memory map (:memory:)
    so tests run instantly and do not corrupt the real .storage/qdrant_db.
    """
    mem_client = QdrantClient(location=":memory:")
    mocker.patch("api.services.rag.indexer.get_qdrant_client", return_value=mem_client)
    # Also reset the module-level singleton so it doesn't leak between tests
    mocker.patch("api.services.rag.indexer._qdrant_client", mem_client)
    return mem_client


# ── LLM Mock ───────────────────────────────────────────────────
@pytest.fixture
def mock_llm(mocker):
    """
    Mock the Ollama LLM to return standard strings instead of requiring
    the GPU to spin up. Patches both the generation engine and the
    query rewriter's import path.
    """
    mock_engine = MagicMock()
    # Support for RAG query engine
    mock_engine.query.return_value = MagicMock(
        response="This is a mocked RAG response.",
        source_nodes=[]
    )
    # Support for Deterministic Router / rewriter completion
    mock_engine.complete.return_value = MagicMock(
        __str__=lambda s: "SEARCH"  # Default to SEARCH for safety
    )
    mocker.patch("api.services.rag.generation.engine.get_llm", return_value=mock_engine)
    return mock_engine


# ── Temporary Storage Dir ──────────────────────────────────────
@pytest.fixture
def tmp_storage(tmp_path, mocker):
    """
    Redirect all config file paths to a temp directory so tests
    never touch the real .storage folder.
    """
    mocker.patch("api.services.config.STORAGE_DIR", tmp_path)
    mocker.patch("api.services.config.APP_SETTINGS_PATH", tmp_path / "app_settings.json")
    mocker.patch("api.services.config.LLM_CONFIG_PATH", tmp_path / "llm_config.json")
    mocker.patch("api.services.config.TOKEN_PATH", tmp_path / "token.json")
    mocker.patch("api.services.config.CREDENTIALS_PATH", tmp_path / "credentials.json")
    mocker.patch("api.services.config.SYNC_CACHE_PATH", tmp_path / "drive_cache.json")
    mocker.patch("api.services.config.FOLDER_CONFIG_PATH", tmp_path / "folder_config.json")
    mocker.patch("api.services.config.LOCAL_FILES_CACHE", tmp_path / "local_files_cache.json")
    mocker.patch("api.services.config.LOCAL_STATS_CACHE", tmp_path / "local_stats_cache.json")
    return tmp_path


# ── Event Bus Cleanup ──────────────────────────────────────────
@pytest.fixture(autouse=True)
def clean_event_bus():
    """Isolate every test from SSE global state."""
    from api.services.event_bus import _clients, _lock
    with _lock:
        _clients.clear()
    yield
    with _lock:
        _clients.clear()


# ── Index Queue Cleanup ────────────────────────────────────────
@pytest.fixture(autouse=True)
def clear_index_queue():
    """Clear the global _index_queue before each test."""
    from api.services.sync_manager import _index_queue
    while not _index_queue.empty():
        try:
            _index_queue.get_nowait()
        except queue.Empty:
            break
    yield
    while not _index_queue.empty():
        try:
            _index_queue.get_nowait()
        except queue.Empty:
            break
