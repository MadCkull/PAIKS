def build_rag_prompt(query: str, chunks: list[dict]) -> str:
    """Build a compact RAG prompt — shorter prompt = faster inference."""
    ctx_parts = []
    for i, c in enumerate(chunks, 1):
        text = c['text'][:600].strip()
        ctx_parts.append(f"[{i}] {text}")
    context = "\n".join(ctx_parts)
    return (
        f"Based on these documents, answer the question helpfully. Cite sources as [1], [2], etc.\n\n"
        f"{context}\n\n"
        f"Q: {query}\nA:"
    )
