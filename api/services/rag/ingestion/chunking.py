import logging
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core.schema import Document, BaseNode

logger = logging.getLogger(__name__)

def get_hierarchical_parser() -> HierarchicalNodeParser:
    """
    Returns a HierarchicalNodeParser. 
    This creates parent chunks (1024 tokens) and child chunks (512 tokens).
    The DB searches the dense/precise children, but LLM context uses the massive parent blocks.
    Overlap of 64 tokens (~12%) preserves sentence continuity across chunk boundaries.
    """
    return HierarchicalNodeParser.from_defaults(
        chunk_sizes=[1024, 512],
        chunk_overlap=64
    )

def chunk_documents(documents: list[Document]) -> list[BaseNode]:
    """
    Takes a list of LlamaIndex Documents and breaks them into a node hierarchy.
    Returns ALL nodes (both parent and leaf nodes) which must all be injected into the VectorStore DB.
    """
    parser = get_hierarchical_parser()
    nodes = parser.get_nodes_from_documents(documents)
    
    # Optional debugging
    leaf_nodes = get_leaf_nodes(nodes)
    logger.info(f"Chunked {len(documents)} documents into {len(nodes)} total nodes ({len(leaf_nodes)} leaves)")
    
    return nodes
