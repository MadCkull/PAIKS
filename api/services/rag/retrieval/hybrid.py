import logging
from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.storage.docstore import SimpleDocumentStore

logger = logging.getLogger(__name__)
from llama_index.core.vector_stores.types import MetadataFilters, ExactMatchFilter

def get_base_retriever(index: VectorStoreIndex, top_k: int = 30) -> VectorIndexRetriever:
    """
    Creates a base retriever for the given index.
    In Qdrant, we currently use dense vectors for stability. 
    Hybrid search is disabled to avoid heavy external model downloads (FastEmbed).
    We fetch top_k=30 because this list will later be filtered by the reranker.
    """
    logger.debug(f"Initializing base VectorIndexRetriever with top_k={top_k}")
    
    # Strictly filter out any soft-disabled files from retrieval
    filters = MetadataFilters(filters=[ExactMatchFilter(key="enabled", value=1)])
    
    return VectorIndexRetriever(
        index=index,
        similarity_top_k=top_k,
        filters=filters,
    )

def get_hybrid_merging_retriever(base_retriever: VectorIndexRetriever, storage_context) -> AutoMergingRetriever:
    """
    Wraps the base hybrid retriever with an AutoMergingRetriever.
    Because we used HierarchicalChunking, the base retriever finds the small precise 256-token child nodes.
    This wrapper detects if multiple children of a parent are matched. If they are, it dynamically
    swaps them out for the 1024-token Parent node so the LLM gets full context.
    """
    logger.debug("Wrapping base retriever with AutoMergingRetriever")
    return AutoMergingRetriever(
        vector_retriever=base_retriever,
        storage_context=storage_context,
        verbose=False,
    )
