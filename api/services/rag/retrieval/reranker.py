import logging
from typing import Optional
from llama_index.core.postprocessor.types import BaseNodePostprocessor

logger = logging.getLogger(__name__)

def get_cross_encoder_reranker(top_n: int = 5) -> Optional[BaseNodePostprocessor]:
    """
    Returns a HuggingFace CrossEncoder reranker.
    A cross-encoder runs the user query and the retrieved document chunk through 
    the transformer model together to calculate a highly precise similarity score.
    This mathematically filters out irrelevant chunks that regular Vector search hallucinated.
    """
    try:
        # Standard LlamaIndex integration for local HuggingFace sentence-transformers
        from llama_index.postprocessor.sbert_rerank import SentenceTransformerRerank
        
        logger.info(f"Loading local bge-reranker-base model. Filtering down to top_{top_n} nodes.")
        
        # We use BAAI's bge-reranker-base as it's the standard for top-tier open-source RAG
        # It will be downloaded to your local huggingface cache on first run.
        reranker = SentenceTransformerRerank(
            model="BAAI/bge-reranker-base",
            top_n=top_n
        )
        return reranker
    except ImportError:
        logger.error(
            "Failed to import SentenceTransformerRerank. "
            "Ensure 'llama-index-postprocessor-sbert-rerank' or 'sentence-transformers' is installed."
        )
        return None
