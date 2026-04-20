"""
RAG Pipeline Debug Tracer
━━━━━━━━━━━━━━━━━━━━━━━━━
Captures the full raw pipeline state for every query and writes it
to .storage/chat.log in a structured, human-readable format.

Each query produces a timestamped block showing:
  1. User query (raw)
  2. Conversation history received
  3. Filename detection result
  4. Query rewriting (before → after)
  5. Retriever configuration
  6. Raw retrieved nodes (ALL of them  -  text, score, metadata)
  7. Reranked nodes (after cross-encoder)
  8. Exact context string assembled for LLM
  9. Full LLM prompt
  10. Raw LLM response
  11. Citation extraction
  12. Final response sent to frontend
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

LOG_DIR = Path(settings.STORAGE_DIR) / "logs" if hasattr(settings, 'STORAGE_DIR') else Path(".storage") / "logs"
LOG_PATH = LOG_DIR / "pipeline.trace"


def _ensure_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _write(text: str):
    """Append text to the chat log file."""
    _ensure_log()
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(text)


def _sep(char="━", width=90):
    return char * width


def _section(title: str, content: str) -> str:
    """Format a named section block."""
    header = f"┌─ {title} {'─' * max(0, 85 - len(title))}"
    footer = f"└{'─' * 89}"
    return f"\n{header}\n{content}\n{footer}\n"


def _json_block(data, indent=2) -> str:
    """Safely serialize data to pretty JSON."""
    try:
        return json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    except Exception as e:
        return f"[Serialization error: {e}]\n{repr(data)}"


class PipelineTracer:
    """Collects data throughout the pipeline and writes a complete trace block."""

    def __init__(self, query: str):
        self.timestamp = datetime.now().isoformat()
        self.query = query
        self.sections = []
        self._start_time = datetime.now()

    def log_section(self, title: str, data):
        """Log a section with structured data."""
        if isinstance(data, (dict, list)):
            content = _json_block(data)
        else:
            content = str(data)
        self.sections.append((title, content))

    def log_text(self, title: str, text: str):
        """Log a section with raw text."""
        self.sections.append((title, text))

    def log_nodes(self, title: str, nodes: list):
        """Log retriever/reranker nodes with full detail."""
        if not nodes:
            self.sections.append((title, "(empty  -  no nodes returned)"))
            return

        entries = []
        for i, node in enumerate(nodes):
            meta = {}
            text = ""
            score = None

            try:
                if hasattr(node, 'node'):
                    # This is a NodeWithScore
                    score = node.score
                    inner = node.node
                    meta = dict(inner.metadata) if hasattr(inner, 'metadata') else {}
                    text = inner.get_content() if hasattr(inner, 'get_content') else str(inner)
                elif hasattr(node, 'metadata'):
                    meta = dict(node.metadata)
                    text = node.get_content() if hasattr(node, 'get_content') else str(node)
                else:
                    text = str(node)
            except Exception as e:
                text = f"[Error extracting node: {e}]"

            entry = {
                "index": i,
                "score": round(score, 6) if score is not None else None,
                "file_name": meta.get("file_name", "?"),
                "file_id": meta.get("file_id", "?"),
                "source": meta.get("source", "?"),
                "section_header": meta.get("section_header", ""),
                "chunk_index": meta.get("chunk_index", "?"),
                "total_chunks": meta.get("total_chunks", "?"),
                "is_summary": meta.get("is_summary", False),
                "text_length": len(text),
                "text_preview": text[:500] + ("..." if len(text) > 500 else ""),
                "full_metadata": meta,
            }
            entries.append(entry)

        self.sections.append((title, _json_block(entries)))

    def flush(self):
        """Write the complete trace block to the log file."""
        elapsed = (datetime.now() - self._start_time).total_seconds()

        lines = []
        lines.append(f"\n{'╔' + _sep('═')}")
        lines.append(f"║  PIPELINE TRACE  -  {self.timestamp}")
        lines.append(f"║  Query: {self.query}")
        lines.append(f"║  Duration: {elapsed:.2f}s")
        lines.append(f"{'╚' + _sep('═')}")

        for title, content in self.sections:
            lines.append(_section(title, content))

        lines.append(f"\n{'─' * 90}\n")

        _write("\n".join(lines))
        logger.info(f"Pipeline trace written to {LOG_PATH}")
