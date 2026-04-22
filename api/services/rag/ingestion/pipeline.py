import re
import logging
from collections import defaultdict
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.node_parser import get_leaf_nodes
from llama_index.core.storage.docstore import SimpleDocumentStore

from api.services.rag.indexer import get_vector_store
from api.services.rag.ingestion.embedder import get_embedder

logger = logging.getLogger(__name__)

# Regex for markdown headings (# Heading, ## Heading, etc.)
_HEADING_RE = re.compile(r'^#{1,6}\s+(.+)', re.MULTILINE)


def _detect_section_header(text: str) -> str:
    """Find the last markdown-style heading in a chunk's text.
    Returns the heading text (without # markers) or empty string.
    """
    matches = _HEADING_RE.findall(text)
    return matches[-1].strip() if matches else ""


def _enrich_node_metadata(nodes: list) -> list:
    """Inject chunk_index, total_chunks, section_header, and is_summary
    into each node's metadata after chunking.
    
    Groups nodes by file_id so each file gets its own sequential numbering.
    The section_header is detected from the chunk's own text content  -  
    if no heading is found in this chunk, it inherits the last known heading
    from previous chunks of the same file.
    """
    # Group nodes by file_id to assign per-file indices
    file_groups = defaultdict(list)
    for node in nodes:
        fid = node.metadata.get("file_id", "unknown")
        file_groups[fid].append(node)
    
    for fid, group in file_groups.items():
        total = len(group)
        last_heading = ""
        
        for idx, node in enumerate(group):
            node.metadata["chunk_index"] = idx
            node.metadata["total_chunks"] = total
            node.metadata["is_summary"] = False
            
            # Detect heading from this chunk's text
            detected = _detect_section_header(node.get_content())
            if detected:
                last_heading = detected
            
            # Use detected heading, or inherit from previous chunk
            node.metadata["section_header"] = last_heading
            
            # Mark point as enabled by default for retrieval
            node.metadata["enabled"] = 1
    
    return nodes


def ingest_nodes_to_collection(nodes: list, collection_name: str):
    """
    Takes a list of Hierarchical Nodes and injects them precisely into a specific Qdrant collection.
    Before storage, enriches all nodes with chunk_index, total_chunks, section_header, and is_summary.
    Automatically handles hybrid construction since the vector store is configured for enable_hybrid=True.
    """
    if not nodes:
        return

    # Enrich metadata before embedding
    nodes = _enrich_node_metadata(nodes)

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
