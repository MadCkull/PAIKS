"""
Query Intelligence Layer for the RAG retrieval pipeline.

Provides two key capabilities:
1. **Query Rewriting**  -  Rewrites user queries into retrieval-optimized form
   using the LLM, bridging the vocabulary gap between user phrasing and
   document content.
2. **Filename Detection**  -  If the query references a known indexed file,
   triggers metadata-filtered retrieval instead of broad vector search.

Both accept optional conversation history for follow-up awareness.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

REWRITE_PROMPT = (
    "You are a search query optimizer for a document retrieval system.\n"
    "Rewrite the following user question into a short, keyword-rich search query "
    "that would retrieve the most relevant document chunks.\n"
    "Return ONLY the rewritten query, nothing else. No explanation.\n\n"
    "{history_block}"
    "User question: {query}\n\n"
    "Rewritten search query:"
)


def rewrite_query(query: str, history: list[dict] | None = None) -> str:
    """Rewrite a user query into a retrieval-optimised form.
    
    Args:
        query: The raw user question.
        history: Optional list of dicts with 'role' and 'content' keys
                 (last N turns for follow-up awareness).
    Returns:
        A keyword-rich search string suitable for embedding-based retrieval.
    """
    from api.services.rag.generation.engine import get_llm

    history_block = ""
    if history:
        turns = []
        for msg in history[-4:]:  # last 4 turns max
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                turns.append(f"{role}: {content}")
        if turns:
            history_block = (
                "Conversation history (for context only):\n"
                + "\n".join(turns)
                + "\n\n"
            )

    prompt = REWRITE_PROMPT.format(history_block=history_block, query=query)
    
    try:
        llm = get_llm()
        response = llm.complete(prompt)
        rewritten = str(response).strip()
        # Sanity: if the LLM returns something too long or weird, fall back
        if not rewritten or len(rewritten) > 500 or "\n" in rewritten:
            logger.debug("Query rewrite returned invalid output, using original")
            return query
        logger.info(f"Query rewritten: '{query}' → '{rewritten}'")
        return rewritten
    except Exception as e:
        logger.warning(f"Query rewrite failed, using original: {e}")
        return query


def detect_filename_query(
    query: str, known_files: list[dict]
) -> Optional[dict]:
    """Check if the user query references a known indexed file.
    
    Args:
        query: The user query string.
        known_files: List of dicts with at least 'file_id', 'file_name',
                     and 'collection' keys (from Qdrant metadata).
    Returns:
        The matching file dict if found, else None.
    """
    q_lower = query.lower()
    
    best_match = None
    best_score = 0
    
    for f in known_files:
        fname = f.get("file_name", "")
        if not fname:
            continue
            
        # Strip extension for matching
        name_no_ext = fname.rsplit(".", 1)[0].lower()
        fname_lower = fname.lower()
        
        # Exact filename match (with or without extension)
        if fname_lower in q_lower or name_no_ext in q_lower:
            score = len(name_no_ext)  # longer match = higher confidence
            if score > best_score:
                best_score = score
                best_match = f
        # Also check if query is a substring of the filename
        elif q_lower in name_no_ext and len(q_lower) > 3:
            score = len(q_lower)
            if score > best_score:
                best_score = score
                best_match = f
    
    if best_match:
        logger.info(f"Filename detected in query: '{best_match.get('file_name')}'")
    
    return best_match


def get_known_files_from_qdrant() -> list[dict]:
    """Fetch a deduplicated list of known indexed files from Qdrant.
    Returns list of dicts with file_id, file_name, source, collection.
    """
    from api.services.rag.indexer import (
        get_qdrant_client, LOCAL_COLLECTION, CLOUD_COLLECTION,
    )
    
    client = get_qdrant_client()
    seen = {}  # file_id -> dict
    
    for col_name in [LOCAL_COLLECTION, CLOUD_COLLECTION]:
        if not client.collection_exists(col_name):
            continue
        try:
            next_offset = None
            while True:
                points, next_offset = client.scroll(
                    collection_name=col_name,
                    limit=100,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                for p in points:
                    pl = p.payload
                    fid = pl.get("file_id")
                    if fid and fid not in seen and not pl.get("is_summary", False):
                        seen[fid] = {
                            "file_id": fid,
                            "file_name": pl.get("file_name", ""),
                            "source": pl.get("source", ""),
                            "collection": col_name,
                        }
                if next_offset is None:
                    break
        except Exception as e:
            logger.debug(f"Error scanning {col_name}: {e}")
    
    return list(seen.values())
