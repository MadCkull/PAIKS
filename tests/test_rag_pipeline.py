"""
Tests for api.services.rag.ingestion.pipeline — Metadata enrichment and ingestion.

Covers:
  - _detect_section_header for markdown heading detection
  - _enrich_node_metadata chunk numbering and section inheritance
  - Section header propagation across chunks of the same file
"""
import pytest
from unittest.mock import MagicMock
from api.services.rag.ingestion.pipeline import (
    _detect_section_header,
    _enrich_node_metadata,
)


class TestSectionHeaderDetection:
    """Validates markdown heading detection in chunk text."""

    def test_h1_heading(self):
        text = "# Introduction\nSome content here."
        assert _detect_section_header(text) == "Introduction"

    def test_h2_heading(self):
        text = "## Related Work\nPrior research includes..."
        assert _detect_section_header(text) == "Related Work"

    def test_h3_heading(self):
        text = "### Sub Section\nDetails."
        assert _detect_section_header(text) == "Sub Section"

    def test_multiple_headings_returns_last(self):
        text = "# First\nContent.\n## Second\nMore content.\n### Third"
        assert _detect_section_header(text) == "Third"

    def test_no_heading_returns_empty(self):
        text = "Just plain text without any headings."
        assert _detect_section_header(text) == ""

    def test_heading_with_extra_spaces(self):
        text = "##   Architecture   \nDetails."
        assert _detect_section_header(text) == "Architecture"


class TestEnrichNodeMetadata:
    """Validates chunk_index, total_chunks, section_header injection."""

    def _make_node(self, file_id, text, metadata=None):
        node = MagicMock()
        node.metadata = metadata or {"file_id": file_id}
        node.metadata["file_id"] = file_id
        node.get_content.return_value = text
        return node

    def test_sequential_chunk_indexing(self):
        nodes = [
            self._make_node("f1", "Chunk zero."),
            self._make_node("f1", "Chunk one."),
            self._make_node("f1", "Chunk two."),
        ]
        enriched = _enrich_node_metadata(nodes)
        assert enriched[0].metadata["chunk_index"] == 0
        assert enriched[1].metadata["chunk_index"] == 1
        assert enriched[2].metadata["chunk_index"] == 2
        assert all(n.metadata["total_chunks"] == 3 for n in enriched)

    def test_is_summary_defaults_to_false(self):
        nodes = [self._make_node("f1", "Content.")]
        enriched = _enrich_node_metadata(nodes)
        assert enriched[0].metadata["is_summary"] is False

    def test_section_header_detected(self):
        nodes = [
            self._make_node("f1", "# Introduction\nSome content."),
            self._make_node("f1", "More content without heading."),
        ]
        enriched = _enrich_node_metadata(nodes)
        assert enriched[0].metadata["section_header"] == "Introduction"
        # Second chunk inherits the heading
        assert enriched[1].metadata["section_header"] == "Introduction"

    def test_section_header_updates_on_new_heading(self):
        nodes = [
            self._make_node("f1", "# Chapter 1\nContent."),
            self._make_node("f1", "## Chapter 2\nMore content."),
        ]
        enriched = _enrich_node_metadata(nodes)
        assert enriched[0].metadata["section_header"] == "Chapter 1"
        assert enriched[1].metadata["section_header"] == "Chapter 2"

    def test_multi_file_independent_indexing(self):
        """Nodes from different files get independent numbering."""
        nodes = [
            self._make_node("f1", "File1 chunk0."),
            self._make_node("f1", "File1 chunk1."),
            self._make_node("f2", "File2 chunk0."),
        ]
        enriched = _enrich_node_metadata(nodes)

        # File 1 nodes
        f1_nodes = [n for n in enriched if n.metadata["file_id"] == "f1"]
        assert f1_nodes[0].metadata["chunk_index"] == 0
        assert f1_nodes[0].metadata["total_chunks"] == 2

        # File 2 nodes
        f2_nodes = [n for n in enriched if n.metadata["file_id"] == "f2"]
        assert f2_nodes[0].metadata["chunk_index"] == 0
        assert f2_nodes[0].metadata["total_chunks"] == 1
