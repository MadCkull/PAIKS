from llama_index.core import PromptTemplate

# Strict instruction prompt for the RAG engine to prevent hallucinations.
QA_PROMPT_TMPL = (
    "Context information from the project files is below.\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Answer the query using ONLY the provided context information.\n"
    "IMPORTANT INSTRUCTIONS:\n"
    "1. If the context information DOES NOT contain a clear, direct answer to the query, you MUST reply EXACTLY with: 'I could not find relevant information regarding this in the indexed files.' Do NOT attempt to guess, infer, or synthesize an answer from unrelated text.\n"
    "2. You MUST provide strict citations for every factual claim. At the end of the relevant sentence, append the citation exactly as it appears in the source metadata, like: [Source: file_name.pdf].\n"
    "Query: {query_str}\n"
    "Answer: "
)

QA_PROMPT = PromptTemplate(QA_PROMPT_TMPL)

# Fast deterministic prompt to classify user intent for routing.
ROUTER_PROMPT_TMPL = (
    "Analyze the following user query and determine if it requires searching internal project documents (code, thesis, project instructions, config files) or if it can be answered using general knowledge or casual conversation.\n"
    'Query: "{query_str}"\n'
    "If it requires searching internal project files or facts, reply strictly with: SEARCH\n"
    "If it is a casual greeting OR a general knowledge question, reply strictly with: GENERAL\n"
    "Classification:"
)

# Standard prompt used when bypassing the RAG system for natural conversation.
GENERAL_CHAT_PROMPT_TMPL = (
    "You are the helpful AI Assistant for the PAIKS project.\n"
    "A user asked or said: \"{query_str}\"\n"
    "Answer them naturally and correctly using your general knowledge. If they are greeting you, greet them back warmly."
)
