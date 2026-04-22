from llama_index.core import PromptTemplate

# ── Unified RAG Prompt with Conversation History ───────────────────────────
# This prompt handles:
# - Document-grounded Q&A with citations
# - Conversation history for follow-up questions
# - Concise, direct responses without meta-commentary

QA_PROMPT_TMPL = (
    "You are PAIKS, a smart and friendly AI assistant with access to the user's files.\n\n"
    "CONTEXT:\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n\n"
    "{query_str}\n\n"
    "Rules:\n"
    "- If the question is conversational or general knowledge (no files needed): Answer it directly and helpfully from your own knowledge.\n\n"
    "- If context is relevant: Use it to answer directly.\n"
    "- If context is empty or clearly unrelated to the question: Answer from your own knowledge. Never say you couldn't find it in files.\n"
    "- For follow-up questions: Use the conversation history above to understand what's being asked, then explain naturally.\n"
    "- Never say \"Based on the context\", \"According to the documents\", or \"The excerpts show\". Just answer directly.\n"
    "- Be concise: 1-3 short paragraphs.\n\n"
    "Answer:"
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
