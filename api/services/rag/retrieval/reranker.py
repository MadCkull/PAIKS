import logging
from typing import Optional
from llama_index.core.postprocessor.types import BaseNodePostprocessor

logger = logging.getLogger(__name__)

# ── Singleton cache: keyed by top_n so different top_n values get their own instance ──
_reranker_cache: dict[int, BaseNodePostprocessor] = {}

def get_cross_encoder_reranker(top_n: int = 5) -> Optional[BaseNodePostprocessor]:
    """
    Returns a cached HuggingFace CrossEncoder reranker (singleton per top_n).
    A cross-encoder runs the user query and the retrieved document chunk through 
    the transformer model together to calculate a highly precise similarity score.
    This mathematically filters out irrelevant chunks that regular Vector search hallucinated.
    
    The model is loaded ONCE and cached in memory. Subsequent calls with the same
    top_n return the cached instance instantly, avoiding the 1-5s cold-start overhead.
    """
    if top_n in _reranker_cache:
        return _reranker_cache[top_n]

    try:
        # Standard LlamaIndex integration for local HuggingFace sentence-transformers
        from llama_index.postprocessor.sbert_rerank import SentenceTransformerRerank
        
        logger.info(f"Loading bge-reranker-base model (first load, will be cached). top_n={top_n}")
        
        # Suppress the harmless 'UNEXPECTED key: roberta.embeddings.position_ids' warning
        # that the base RoBERTa checkpoint emits when loaded for sequence classification.
        _transformers_logger = logging.getLogger("transformers")
        _st_logger = logging.getLogger("sentence_transformers")
        _prev_tf_level = _transformers_logger.level
        _prev_st_level = _st_logger.level
        _transformers_logger.setLevel(logging.ERROR)
        _st_logger.setLevel(logging.ERROR)
        
        try:
            # We use BAAI's bge-reranker-base as it's the standard for top-tier open-source RAG
            # It will be downloaded to your local huggingface cache on first run.
            reranker = SentenceTransformerRerank(
                model="BAAI/bge-reranker-base",
                top_n=top_n
            )
        finally:
            # Restore original log levels so genuine errors are still visible
            _transformers_logger.setLevel(_prev_tf_level)
            _st_logger.setLevel(_prev_st_level)
        
        _reranker_cache[top_n] = reranker
        logger.info("Reranker model loaded and cached successfully.")
        return reranker
    except ImportError:
        logger.error(
            "Failed to import SentenceTransformerRerank. "
            "Ensure 'llama-index-postprocessor-sbert-rerank' or 'sentence-transformers' is installed."
        )
        return None


def warmup_reranker():
    """Pre-load the reranker model at application startup.
    Called from ApiConfig.ready() so the first search query is instant.
    """
    logger.info("Warming up reranker model at startup...")
    get_cross_encoder_reranker(top_n=5)
    get_cross_encoder_reranker(top_n=8)  # Also used in file-specific queries
