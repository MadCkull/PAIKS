import logging
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.llms.ollama import Ollama
from llama_index.core import PromptTemplate

from api.services.config import load_llm_config
from api.services.rag.generation.prompts import QA_PROMPT, ROUTER_PROMPT_TMPL, GENERAL_CHAT_PROMPT_TMPL

logger = logging.getLogger(__name__)

def get_llm() -> Ollama:
    """Instantiate the local LLM using LlamaIndex Ollama integration."""
    cfg = load_llm_config()
    model = cfg.get("model", "llama3.2")
    base_url = cfg.get("base_url", "http://localhost:11434")
    
    logger.info(f"Connecting to generation LLM {model} at {base_url}")
    return Ollama(model=model, base_url=base_url, request_timeout=120.0)

def classify_intent(query: str) -> str:
    """
    Deterministically classifies the user query as SEARCH or GENERAL.
    This bypasses the need for complex agent reasoning loops.
    """
    llm = get_llm()
    prompt = ROUTER_PROMPT_TMPL.format(query_str=query)
    response = llm.complete(prompt)
    classification = str(response).strip().upper()
    
    if "SEARCH" in classification:
        return "SEARCH"
    return "GENERAL"

def get_general_response(query: str) -> str:
    """Generates a natural chat response for non-RAG queries."""
    llm = get_llm()
    prompt = GENERAL_CHAT_PROMPT_TMPL.format(query_str=query)
    # Using LlamaIndex direct complete for conversational bypass
    response = llm.complete(prompt)
    return str(response).strip()

def build_query_engine(merging_retriever, reranker_node_postprocessor) -> RetrieverQueryEngine:
    """
    Assembles the final intelligent RAG engine for factual document retrieval.
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
