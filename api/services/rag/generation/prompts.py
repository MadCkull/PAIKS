from llama_index.core import PromptTemplate

# Advanced RAG prompt incorporating Chain-of-Thought and Condensed Context principles.
# Optimized based on industry best practices for accuracy and formatting consistency.
QA_PROMPT_TMPL = (
    "Context information from the project files is provided below.\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Answer the user query using ONLY the provided context. Follow these strict steps:\n"
    "Step 1: Analyze the context to find direct evidence even if it's partially relevant.\n"
    "Step 2: If the evidence is missing, state clearly that you do not have enough specific documentation.\n"
    "Step 3: Draft an answer that is concise and factual.\n"
    "Step 4: Strictly cite every factual claim by appending a source tag at the end of the citation. "
    "Use EXACTLY this format: [Source: file_name.ext].\n\n"
    "RULES:\n"
    "- If no answer is possible, reply EXACTLY with: 'I could not find relevant information regarding this in the indexed files.'\n"
    "- DO NOT mention 'Step 1' or 'Step 2' in your final response. Only provide the final Answer.\n"
    "- Keep citations within the text, not at the end of the message.\n\n"
    "Query: {query_str}\n"
    "Answer: "
)

QA_PROMPT = PromptTemplate(QA_PROMPT_TMPL)

# Fast deterministic prompt to classify user intent for routing.
ROUTER_PROMPT_TMPL = (
    "Analyze the following user query. Determine if it relates to specific facts, people, documents, or data that would be in internal project files.\n"
    'Query: "{query_str}"\n\n'
    "RULES:\n"
    "- If the query contains a specific name (e.g. 'Umar Draz', 'Hassan Ali'), reply: SEARCH\n"
    "- If it asks for technical details, dates, or specific content, reply: SEARCH\n"
    "- If it is a generic greeting ('hi', 'hey'), or a broad general knowledge question ('how do I cook?'), reply: GENERAL\n\n"
    "Reply with ONLY one word: SEARCH or GENERAL.\n"
    "Classification:"
)

# Standard prompt used when bypassing the RAG system for natural conversation.
GENERAL_CHAT_PROMPT_TMPL = (
    "You are the helpful AI Assistant for the PAIKS project.\n"
    "A user asked or said: \"{query_str}\"\n"
    "Answer them naturally and correctly using your general knowledge. If they are greeting you, greet them back warmly."
)
