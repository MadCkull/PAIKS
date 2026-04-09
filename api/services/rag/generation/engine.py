import re
import logging
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.llms.ollama import Ollama
from llama_index.core import PromptTemplate

from api.services.config import load_llm_config
from api.services.rag.generation.prompts import QA_PROMPT

logger = logging.getLogger(__name__)


def get_llm() -> Ollama:
    """Instantiate the local LLM using LlamaIndex Ollama integration.
    Temperature=0 ensures deterministic, focused factual responses.
    """
    cfg = load_llm_config()
    model = cfg.get("model", "llama3.2")
    base_url = cfg.get("base_url", "http://localhost:11434")
    
    logger.info(f"Connecting to generation LLM {model} at {base_url}")
    return Ollama(
        model=model,
        base_url=base_url,
        request_timeout=120.0,
        temperature=0.0,
    )


def build_query_engine(merging_retriever, reranker_node_postprocessor) -> RetrieverQueryEngine:
    """
    Assembles the final intelligent RAG engine for factual document retrieval.
    Uses the unified prompt that handles both RAG context and general knowledge.
    """
    llm = get_llm()
    
    engine = RetrieverQueryEngine.from_args(
        retriever=merging_retriever,
        llm=llm,
        node_postprocessors=[reranker_node_postprocessor] if reranker_node_postprocessor else [],
        text_qa_template=QA_PROMPT,
        response_mode="compact"
    )
    return engine


# ── Similarity Gate ─────────────────────────────────────────────────────────

def should_use_rag(source_nodes: list, threshold: float = 0.30) -> bool:
    """Check if the top retrieval result meets the quality threshold.
    
    If the best reranked score is below the threshold, the retrieved context
    is likely irrelevant and should not be passed to the LLM.
    
    Args:
        source_nodes: List of scored nodes from the retriever/reranker.
        threshold: Minimum score to consider results relevant (default 0.30).
    Returns:
        True if context is worth using, False if we should skip RAG.
    """
    if not source_nodes:
        return False
    
    best_score = max(
        (node.score for node in source_nodes if node.score is not None),
        default=0.0
    )
    
    logger.info(f"Similarity gate: best_score={best_score:.3f}, threshold={threshold}")
    return best_score >= threshold


# ── Citation Extraction ─────────────────────────────────────────────────────

_CITATION_PATTERN = re.compile(r'\[Source:\s*(.+?)(?:\s*→\s*(.+?))?\]')


def extract_citations(response_text: str) -> tuple[str, list[dict]]:
    """Parse [Source: filename → section] tags from LLM output.
    
    Returns:
        A tuple of (clean_response_text, list_of_citation_dicts).
        Each citation dict has 'filename' and optional 'section' keys.
    """
    matches = _CITATION_PATTERN.findall(response_text)
    citations = []
    seen = set()
    
    for filename, section in matches:
        key = f"{filename.strip()}|{section.strip()}"
        if key not in seen:
            seen.add(key)
            citations.append({
                "filename": filename.strip(),
                "section": section.strip() if section else "",
            })
    
    return response_text, citations
