"""
Tests for api.services.rag.tracer — Pipeline debug tracer.

Covers:
  - PipelineTracer initialization and section logging
  - Flush writes to the log file
  - Node logging with metadata extraction
  - JSON serialization safety
"""
import pytest
from unittest.mock import patch, MagicMock
from api.services.rag.tracer import PipelineTracer, _section, _json_block


class TestPipelineTracer:
    """Validates the debug trace writer."""

    def test_initialization(self):
        tracer = PipelineTracer("What is PAIKS?")
        assert tracer.query == "What is PAIKS?"
        assert tracer.sections == []

    def test_log_section_with_dict(self):
        tracer = PipelineTracer("test")
        tracer.log_section("Test Section", {"key": "value"})
        assert len(tracer.sections) == 1
        assert tracer.sections[0][0] == "Test Section"

    def test_log_section_with_string(self):
        tracer = PipelineTracer("test")
        tracer.log_section("Text Section", "plain text content")
        assert len(tracer.sections) == 1

    def test_log_text(self):
        tracer = PipelineTracer("test")
        tracer.log_text("RAW OUTPUT", "Hello world response")
        assert tracer.sections[0][1] == "Hello world response"

    def test_log_nodes_empty(self):
        tracer = PipelineTracer("test")
        tracer.log_nodes("Empty Nodes", [])
        assert "(empty" in tracer.sections[0][1]

    def test_log_nodes_with_scored_node(self):
        tracer = PipelineTracer("test")

        mock_inner = MagicMock()
        mock_inner.metadata = {"file_name": "test.pdf", "file_id": "f1", "source": "local"}
        mock_inner.get_content.return_value = "Sample content text."

        mock_node = MagicMock()
        mock_node.node = mock_inner
        mock_node.score = 0.85

        tracer.log_nodes("Scored Nodes", [mock_node])
        assert len(tracer.sections) == 1
        assert "test.pdf" in tracer.sections[0][1]

    def test_flush_writes_file(self, tmp_path):
        with patch("api.services.rag.tracer.LOG_PATH", tmp_path / "chat.log"):
            with patch("api.services.rag.tracer.LOG_DIR", tmp_path):
                tracer = PipelineTracer("test query")
                tracer.log_section("Section 1", {"data": "value"})
                tracer.flush()

                log_content = (tmp_path / "chat.log").read_text(encoding="utf-8")
                assert "PIPELINE TRACE" in log_content
                assert "test query" in log_content


class TestHelperFunctions:
    """Validates tracer utility functions."""

    def test_section_formatting(self):
        result = _section("Test Title", "content body")
        assert "Test Title" in result
        assert "content body" in result

    def test_json_block_normal(self):
        result = _json_block({"key": "value"})
        assert '"key"' in result
        assert '"value"' in result

    def test_json_block_with_unserializable(self):
        """Should handle non-JSON-serializable objects gracefully."""
        result = _json_block({"date": object()})
        # Should not crash — uses default=str
        assert "object" in result.lower() or "Serialization" not in result
