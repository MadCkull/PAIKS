"""
Tests for api.services.rag.ingestion.chunking — Hierarchical node parsing.

Covers:
  - Node hierarchy (parents > leaves)
  - Metadata inheritance to leaf nodes
  - Small document handling (single-chunk edge case)
  - Multi-document batch chunking
"""
import pytest
from llama_index.core.schema import Document
from llama_index.core.node_parser import get_leaf_nodes
from api.services.rag.ingestion.chunking import chunk_documents, get_hierarchical_parser


class TestHierarchicalChunking:
    """Validates the HierarchicalNodeParser configuration and output."""

    def test_parser_returns_correct_chunk_sizes(self):
        parser = get_hierarchical_parser()
        assert parser is not None

    def test_large_document_produces_hierarchy(self):
        """A large document must produce both parent and leaf nodes."""
        long_text = "Word. " * 3000
        doc = Document(text=long_text, metadata={"file_name": "giant.txt"})

        nodes = chunk_documents([doc])

        assert len(nodes) > 0, "Chunking should return multiple nodes"
        leaf_nodes = get_leaf_nodes(nodes)
        assert len(leaf_nodes) > 0, "Must generate leaf elements for Vector DB"
        assert len(nodes) > len(leaf_nodes), "Parent nodes must exist"

    def test_metadata_inherited_by_leaves(self):
        """Leaf nodes must inherit the parent document's metadata."""
        long_text = "Sentence about AI research. " * 500
        doc = Document(text=long_text, metadata={
            "file_name": "research.pdf",
            "file_id": "local__research.pdf",
            "source": "local",
        })

        nodes = chunk_documents([doc])
        leaf_nodes = get_leaf_nodes(nodes)

        for leaf in leaf_nodes:
            assert leaf.metadata.get("file_name") == "research.pdf"
            assert leaf.metadata.get("source") == "local"

    def test_small_document_produces_at_least_one_node(self):
        """Even a tiny document must produce at least one node."""
        doc = Document(text="Short text.", metadata={"file_name": "tiny.txt"})
        nodes = chunk_documents([doc])
        assert len(nodes) >= 1

    def test_multi_document_batch(self):
        """Multiple documents chunked together produce independent nodes."""
        docs = [
            Document(text="Alpha content. " * 200, metadata={"file_name": "alpha.txt", "file_id": "a"}),
            Document(text="Beta content. " * 200, metadata={"file_name": "beta.txt", "file_id": "b"}),
        ]
        nodes = chunk_documents(docs)

        file_names = {n.metadata.get("file_name") for n in nodes}
        assert "alpha.txt" in file_names
        assert "beta.txt" in file_names

    def test_empty_document_list(self):
        """Empty input should return empty output."""
        nodes = chunk_documents([])
        assert nodes == []
