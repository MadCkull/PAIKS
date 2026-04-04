import logging
from llama_index.embeddings.ollama import OllamaEmbedding
from api.services.config import load_llm_config

logger = logging.getLogger(__name__)

def get_embedder() -> OllamaEmbedding:
    """
    Returns the OllamaEmbedding configuration to use nomic-embed-text locally.
    This guarantees high-quality 8192-token dense vectors offline.
    """
    app_cfg = load_llm_config()
    base_url = app_cfg.get("base_url", "http://localhost:11434")
    
    # We enforce nomic-embed-text as the professional standard for this pipeline
    embed_model_name = "nomic-embed-text"
    
    logger.info(f"Connecting to Ollama embedder {embed_model_name} at {base_url}")
    return OllamaEmbedding(
        model_name=embed_model_name,
        base_url=base_url,
    )
