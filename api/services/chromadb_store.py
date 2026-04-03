import threading
import logging
from .config import CHROMA_PATH

logger = logging.getLogger(__name__)

_chroma_client = None
_chroma_collection = None
_chroma_lock = threading.Lock()

def get_collection():
    global _chroma_client, _chroma_collection
    if _chroma_collection is None:
        with _chroma_lock:
            if _chroma_collection is None:
                import chromadb
                from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
                _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
                _chroma_collection = _chroma_client.get_or_create_collection(
                    name="paiks_docs",
                    embedding_function=DefaultEmbeddingFunction(),
                    metadata={"hnsw:space": "cosine"},
                )
    return _chroma_collection

def prewarm_chroma():
    try:
        col = get_collection()
        if col.count() > 0:
            col.query(query_texts=["warmup"], n_results=1, include=["documents"])
        logger.info(f"ChromaDB pre-warmed ({col.count()} chunks)")
    except Exception as e:
        logger.warning(f"ChromaDB pre-warm failed (non-fatal): {e}")
