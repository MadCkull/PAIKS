import re

def split_sentences(text):
    """Split text into sentences using simple heuristics."""
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in parts if s.strip()]

def chunk_text(text, chunk_size=1000, overlap=200):
    """Split text into overlapping sentence-aware chunks."""
    text = " ".join(text.split())
    if not text:
        return []

    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks = []
    current = ""

    for sent in sentences:
        if len(sent) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            while start < len(sent):
                end = start + chunk_size
                chunks.append(sent[start:end].strip())
                start = end - overlap
            continue

        if len(current) + len(sent) + 1 > chunk_size:
            chunks.append(current.strip())
            if len(current) > overlap:
                current = current[-overlap:].lstrip() + " " + sent
            else:
                current = sent
        else:
            current = (current + " " + sent).strip() if current else sent

    if current.strip():
        chunks.append(current.strip())

    return chunks
