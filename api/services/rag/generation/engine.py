import logging
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.llms.ollama import Ollama

from api.services.config import load_llm_config
from api.services.rag.generation.prompts import QA_PROMPT, AGENT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

def get_llm() -> Ollama:
    """Instantiate the local LLM using LlamaIndex Ollama integration."""
    cfg = load_llm_config()
    model = cfg.get("model", "llama3.2")
    base_url = cfg.get("base_url", "http://localhost:11434")
    
    logger.info(f"Connecting to generation LLM {model} at {base_url}")
    return Ollama(model=model, base_url=base_url, request_timeout=120.0)

def build_agent(merging_retriever, reranker_node_postprocessor) -> ReActAgent:
    """
    Assembles the final intelligent RAG ReAct Agent:
    1. Fetches parents via merging_retriever
    2. Filters precisely via reranker post-processor
    3. Wraps the engine into a tool for the ReAct Agent.
    """
    llm = get_llm()
    
    # The factual engine used strictly for retrieving documents
    query_engine = RetrieverQueryEngine.from_args(
        retriever=merging_retriever,
        llm=llm,
        node_postprocessors=[reranker_node_postprocessor] if reranker_node_postprocessor else [],
        text_qa_template=QA_PROMPT,
        response_mode="compact" # Efficiently packs context
    )
    
    # Declare the RAG engine as a functional tool
    rag_tool = QueryEngineTool(
        query_engine=query_engine,
        metadata=ToolMetadata(
            name="Search_Project_Files",
            description="Execute this tool to retrieve strictly factual information, context, code, or documentation from the project files. ALWAYS use this if the user asks a question that requires facts, data, or project-specific knowledge."
        )
    )
    
    # Create the ReAct agent
    agent = ReActAgent.from_tools(
        [rag_tool],
        llm=llm,
        verbose=True,
        system_prompt=AGENT_SYSTEM_PROMPT
    )
    
    return agent
