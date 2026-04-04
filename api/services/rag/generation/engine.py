import logging
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.llms.ollama import Ollama

from api.services.config import load_llm_config
from api.services.rag.generation.prompts import QA_PROMPT

logger = logging.getLogger(__name__)

def get_llm() -> Ollama:
    """Instantiate the local LLM using LlamaIndex Ollama integration."""
    cfg = load_llm_config()
    model = cfg.get("model", "llama3.2")
    base_url = cfg.get("base_url", "http://localhost:11434")
    
    logger.info(f"Connecting to generation LLM {model} at {base_url}")
    return Ollama(model=model, base_url=base_url, request_timeout=120.0)

def build_query_engine(merging_retriever, reranker_node_postprocessor) -> RetrieverQueryEngine:
    """
    Assembles the final intelligent RAG engine:
    1. Fetches parents via merging_retriever
    2. Filters precisely via reranker post-processor
    3. Feeds context locally to Ollama LLM
    """
    llm = get_llm()
    
    # We assemble the Query Engine manually because we are using a complex retriever pipeline
    engine = RetrieverQueryEngine.from_args(
        retriever=merging_retriever,
        llm=llm,
        node_postprocessors=[reranker_node_postprocessor] if reranker_node_postprocessor else [],
        text_qa_template=QA_PROMPT,
        response_mode="compact" # Efficiently packs context
    )
    return engine
