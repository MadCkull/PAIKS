from llama_index.core import PromptTemplate

# Strict instruction prompt to prevent the LLM from hallucinating answers 
# outside of the provided context, and enforcing rigorous citations.
QA_PROMPT_TMPL = (
    "Context information is below.\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Given the context information and not prior knowledge, answer the query.\n"
    "IMPORTANT INSTRUCTIONS:\n"
    "1. You must answer ONLY using the provided context.\n"
    "2. If the answer is not contained within the context, simply state 'I cannot answer this based on the provided documents.'\n"
    "3. You MUST provide strict citations for every factual claim. At the end of the relevant sentence, append the citation exactly as it appears in the source metadata, like: [Source: file_name.pdf].\n"
    "Query: {query_str}\n"
    "Answer: "
)

QA_PROMPT = PromptTemplate(QA_PROMPT_TMPL)
