import pytest
from llama_index.core.schema import Document
from llama_index.core.node_parser import get_leaf_nodes
from api.services.rag.ingestion.chunking import chunk_documents, get_hierarchical_parser

def test_hierarchical_chunking_ratios():
    """
    Validates that a very long document is properly sliced into a Hierarchical Node structure
    where Large Parent chunks encompass smaller Leaf chunks.
    """
    long_text = "Word. " * 3000  # Synthesize a massive document
    doc = Document(text=long_text, metadata={"file_name": "giant.txt"})
    
    nodes = chunk_documents([doc])
    
    assert len(nodes) > 0, "Chunking should return multiple nodes"
    
    leaf_nodes = get_leaf_nodes(nodes)
    assert len(leaf_nodes) > 0, "Must generate leaf elements for Vector DB"
    
    # In hierarchical parsing, the total node count includes both parents and children.
    # Therefore, total nodes must be greater than just the leaves.
    assert len(nodes) > len(leaf_nodes), "Parent nodes must exist"
    
    # Verify metadata is perfectly inherited downwards
    sample_leaf = leaf_nodes[0]
    assert sample_leaf.metadata.get("file_name") == "giant.txt"
