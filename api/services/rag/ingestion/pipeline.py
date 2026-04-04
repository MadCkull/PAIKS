import logging
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.node_parser import get_leaf_nodes
from llama_index.core.storage.docstore import SimpleDocumentStore

from api.services.rag.indexer import get_vector_store
from api.services.rag.ingestion.embedder import get_embedder

logger = logging.getLogger(__name__)

def ingest_nodes_to_collection(nodes: list, collection_name: str):
    """
    Takes a list of Hierarchical Nodes and injects them precisely into a specific Qdrant collection.
    Automatically handles hybrid construction since the vector store is configured for enable_hybrid=True.
    """
    if not nodes:
        return

    logger.info(f"Ingesting {len(nodes)} nodes to collection '{collection_name}'...")
    
    # We must construct a LlamaIndex VectorStoreIndex explicitly
    vector_store = get_vector_store(collection_name)
    embed_model = get_embedder()
    
    # When using HierarchicalChunking, we must also persist the relationship map in a local docstore
    # so the retrieval phase can find parent nodes. We'll store it linked to Qdrant.
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    # We add all nodes to doc store so relationships exist
    storage_context.docstore.add_documents(nodes)

    # Note: Only leaf nodes are indexed explicitly into the vector DB for searching.
    # The parent nodes just live in the docstore.
    leaf_nodes = get_leaf_nodes(nodes)
    
    # Build vector index over the leaf nodes
    VectorStoreIndex(
        nodes=leaf_nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        show_progress=False
    )
    
    logger.info(f"Ingestion complete: {len(leaf_nodes)} leaf nodes embedded into {collection_name}")
