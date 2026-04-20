import os
import logging
from pathlib import Path
from qdrant_client import QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore

logger = logging.getLogger(__name__)

# Base directory for the embedded Qdrant DB
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / ".storage"
QDRANT_PATH = STORAGE_DIR / "databases" / "vectors"

# The names of our strictly separated collections
CLOUD_COLLECTION = "paiks_cloud_index"
LOCAL_COLLECTION = "paiks_local_index"

# Global client singleton pattern to prevent multiple locks
_qdrant_client = None

def get_qdrant_client() -> QdrantClient:
    """Return a singleton instance of the embedded Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        QDRANT_PATH.mkdir(parents=True, exist_ok=True)
        # Using persistent memory-mapped mode (offline, no docker)
        _qdrant_client = QdrantClient(path=str(QDRANT_PATH))
        logger.info(f"Initialized Embedded QdrantClient at {str(QDRANT_PATH)}")
    return _qdrant_client

def get_vector_store(collection_name: str) -> QdrantVectorStore:
    """
    Return a LlamaIndex VectorStore connected to the specific Qdrant collection.
    By using 'enable_hybrid=True', Qdrant automatically generates sparse vectors (BM25)
    alongside thick dense vectors inside the localized DB.
    """
    client = get_qdrant_client()
    return QdrantVectorStore(
        collection_name=collection_name, 
        client=client, 
        enable_hybrid=True
    )
