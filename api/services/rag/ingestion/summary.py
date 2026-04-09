"""
Document-level summary generation for the RAG pipeline.

Generates a concise multi-paragraph summary per document using the local LLM,
then stores it as a special node in Qdrant with is_summary=True. This enables
document-level queries like "Summarize the PAIKS project file" to have a high
semantic match, solving the chunk-level retrieval mismatch for broad questions.

Summaries are generated manually per-file from the Knowledge Inspector UI.
"""
import logging
from llama_index.core.schema import TextNode
from api.services.rag.ingestion.embedder import get_embedder
from api.services.rag.indexer import get_vector_store, get_qdrant_client

logger = logging.getLogger(__name__)

SUMMARY_PROMPT_TMPL = (
    'You are summarizing a document called "{filename}".\n'
    "Write a comprehensive but concise summary (3-5 paragraphs) covering the main topics, "
    "purpose, and key information in this document.\n"
    "Only use the provided content. Do not invent any information.\n\n"
    "Content:\n{content}\n\n"
    "Summary:"
)


def generate_summary_text(chunks_text: list[str], filename: str) -> str:
    """Call the local LLM to produce a document summary from chunk texts.
    Uses the first ~20 chunks (to stay within context window limits).
    """
    from api.services.rag.generation.engine import get_llm

    combined = "\n\n".join(chunks_text[:20])
    # Trim to ~6000 chars to stay safely within Llama 3.2's context window
    if len(combined) > 6000:
        combined = combined[:6000] + "\n...[truncated]"

    prompt = SUMMARY_PROMPT_TMPL.format(filename=filename, content=combined)
    llm = get_llm()
    response = llm.complete(prompt)
    return str(response).strip()


def store_summary_node(
    summary_text: str,
    file_id: str,
    filename: str,
    source: str,
    collection_name: str,
    extra_metadata: dict | None = None,
):
    """Embed and store a summary node in Qdrant for the given file.
    If a summary already exists for this file_id it is replaced.
    """
    # Build metadata
    meta = {
        "file_id": file_id,
        "file_name": filename,
        "source": source,
        "is_summary": True,
        "chunk_index": -1,
        "total_chunks": 0,
        "section_header": "Document Summary",
    }
    if extra_metadata:
        meta.update(extra_metadata)

    # Remove any existing summary for this file first
    _delete_existing_summary(file_id, collection_name)

    # Create a TextNode with the summary
    node = TextNode(
        text=summary_text,
        metadata=meta,
        excluded_llm_metadata_keys=["file_id", "source", "is_summary", "chunk_index", "total_chunks"],
        excluded_embed_metadata_keys=["file_id", "is_summary", "chunk_index", "total_chunks"],
    )

    # Embed and insert
    embedder = get_embedder()
    embedding = embedder.get_text_embedding(summary_text)
    node.embedding = embedding

    vector_store = get_vector_store(collection_name)
    vector_store.add([node])

    logger.info(f"Stored summary node for '{filename}' in {collection_name}")


def _delete_existing_summary(file_id: str, collection_name: str):
    """Remove any existing summary node for the given file_id from Qdrant."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    client = get_qdrant_client()
    if not client.collection_exists(collection_name):
        return

    try:
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(key="is_summary", match=MatchValue(value=True)),
                    FieldCondition(key="file_id", match=MatchValue(value=file_id)),
                ]
            ),
        )
    except Exception as e:
        logger.debug(f"Could not delete old summary for {file_id}: {e}")


def get_existing_summary(file_id: str, collection_name: str) -> str | None:
    """Retrieve the summary text for a file_id if it exists in Qdrant."""
    import json
    client = get_qdrant_client()
    if not client.collection_exists(collection_name):
        return None

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        results, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="is_summary", match=MatchValue(value=True)),
                    FieldCondition(key="file_id", match=MatchValue(value=file_id)),
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if results:
            payload = results[0].payload
            text = payload.get("text") or payload.get("content")
            if not text and "_node_content" in payload:
                try:
                    node_data = json.loads(payload["_node_content"])
                    text = node_data.get("text")
                except Exception:
                    pass
            return text
    except Exception as e:
        logger.debug(f"Could not fetch summary for {file_id}: {e}")

    return None
