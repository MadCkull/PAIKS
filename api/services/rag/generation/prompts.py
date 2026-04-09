from llama_index.core import PromptTemplate

# ── Unified RAG Prompt with Conversation History ───────────────────────────
# This prompt handles:
# - Document-grounded Q&A with citations
# - Conversation history for follow-up questions
# - Concise, direct responses without meta-commentary

QA_PROMPT_TMPL = (
    "You are PAIKS, a concise and accurate AI assistant.\n\n"
    "DOCUMENT EXCERPTS:\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n\n"
    "RULES:\n"
    "1. You MUST use the CONVERSATION HISTORY (if provided below) to understand context, follow-ups, and answer questions about the conversation itself.\n"
    "2. Answer the user's question using the DOCUMENT EXCERPTS and the CONVERSATION HISTORY.\n"
    "3. Cite every fact from excerpts with [Source: filename.ext] or [Source: filename.ext → Section Name]. Do not cite conversation history.\n"
    "4. Be CONCISE — answer in 1-3 short paragraphs. Do NOT write essays.\n"
    "5. If the history or excerpts contain the answer, USE THEM. Do not say you cannot find it.\n"
    "6. If the answer is completely missing, say so briefly and answer from your own knowledge.\n"
    "7. NEVER say things like 'It seems like you provided context' or 'Based on the context'. Just answer directly.\n"
    "8. Do NOT repeat the question back. Do NOT add filler phrases.\n\n"
    "{query_str}\n"
    "Answer: "
)

QA_PROMPT = PromptTemplate(QA_PROMPT_TMPL)


def build_query_with_history(query: str, history: list[dict] | None = None) -> str:
    """Build the query string, prepending conversation history if available.
    
    This injects history into the {query_str} template variable since
    LlamaIndex's RetrieverQueryEngine only supports {context_str} and {query_str}.
    """
    if not history:
        return f"Question: {query}"
    
    # Build a compact history block (last 6 messages)
    turns = []
    for msg in history[-6:]:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if content:
            label = "User" if role == "user" else "Assistant"
            turns.append(f"{label}: {content}")
    
    if not turns:
        return f"Question: {query}"
    
    history_block = "\n".join(turns)
    return (
        f"--- CONVERSATION HISTORY ---\n"
        f"{history_block}\n"
        f"----------------------------\n\n"
        f"Question: {query}"
    )
