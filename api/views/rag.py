import json
import logging
import os
import pathlib
import time
from django.http import JsonResponse

from api.services.google_auth import get_creds
from api.services.google_drive import drive_service
from api.services.config import load_cache, load_app_settings, LOCAL_ALLOWED_EXTENSIONS
from api.views.drive import refresh_local_stats

# --- NEW RAG ARCHITECTURE IMPORTS ---
from api.services.rag.indexer import get_vector_store, CLOUD_COLLECTION, LOCAL_COLLECTION
from api.services.rag.ingestion.parsers import parse_cloud_file, parse_local_file
from api.services.rag.ingestion.chunking import chunk_documents
from api.services.rag.ingestion.pipeline import ingest_nodes_to_collection
from api.services.rag.retrieval.hybrid import get_base_retriever
from api.services.rag.retrieval.reranker import get_cross_encoder_reranker
from api.services.rag.generation.engine import build_query_engine, classify_intent, get_general_response
from api.services.rag.ingestion.embedder import get_embedder

from llama_index.core import VectorStoreIndex, QueryBundle
from llama_index.core.retrievers import BaseRetriever

logger = logging.getLogger(__name__)

_ingest_progress = {"running": False, "processed": 0, "total": 0, "done": False, "error": None}

def status(request):
    """
    Returns the status of the Qdrant DB points.
    """
    try:
        from api.services.rag.indexer import get_qdrant_client
        client = get_qdrant_client()
        local_count = client.get_collection(LOCAL_COLLECTION).points_count if client.collection_exists(LOCAL_COLLECTION) else 0
        cloud_count = client.get_collection(CLOUD_COLLECTION).points_count if client.collection_exists(CLOUD_COLLECTION) else 0
        total_chunks = local_count + cloud_count
        return JsonResponse({
            "indexed": total_chunks > 0,
            "total_chunks": total_chunks,
            "ingest_running": _ingest_progress["running"],
            "ingest_progress": _ingest_progress,
        })
    except Exception as e:
        logger.warning(f"RAG status check failed: {e}")
        return JsonResponse({"indexed": False, "total_chunks": 0, "ingest_running": False})


def ingest(request):
    global _ingest_progress

    if _ingest_progress.get("running"):
        return JsonResponse({"error": "Ingest already running. Check /api/rag/status for progress."}, status=409)

    app_settings = load_app_settings()
    cloud_enabled = app_settings.get("cloud_enabled", True)
    local_enabled = app_settings.get("local_enabled", True)
    local_root = app_settings.get("local_root_path")

    cloud_docs = []
    local_docs = []

    # ── Gather Cloud Files ──────────────────────────────────
    if cloud_enabled:
        creds = get_creds()
        if creds:
             service = drive_service(creds)
             cache = load_cache()
             for f in cache.get("files", []):
                cloud_docs.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "mime": f.get("mimeType"),
                    "link": f.get("webViewLink", ""),
                    "modified": f.get("modifiedTime", ""),
                })

    # ── Gather Local Files ──────────────────────────────────
    if local_enabled and local_root and os.path.exists(local_root):
        for root, dirs, filenames in os.walk(local_root):
            for filename in filenames:
                ext = pathlib.Path(filename).suffix.lower()
                if ext in LOCAL_ALLOWED_EXTENSIONS:
                    full_path = os.path.join(root, filename)
                    local_docs.append({
                        "id": f"local__{full_path}",
                        "name": filename,
                        "local_path": full_path,
                        "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(full_path))),
                    })

    if not cloud_docs and not local_docs:
        return JsonResponse({"error": "No files found to process."}, status=400)

    total_files = len(cloud_docs) + len(local_docs)
    _ingest_progress = {"running": True, "processed": 0, "total": total_files, "done": False, "error": None}

    processed, skipped, total_chunks = 0, 0, 0
    errors = []

    # ── Process Cloud Collection ────────────────────────────
    if cloud_docs:
        service = drive_service(get_creds())
        parsed_docs = []
        for f in cloud_docs:
            doc = parse_cloud_file(service, f)
            if doc:
                parsed_docs.append(doc)
            else:
                skipped += 1
            processed += 1
            _ingest_progress["processed"] = processed

        if parsed_docs:
            try:
                nodes = chunk_documents(parsed_docs)
                total_chunks += len(nodes)
                ingest_nodes_to_collection(nodes, CLOUD_COLLECTION)
            except Exception as e:
                logger.error(f"Cloud ingestion failed: {e}")
                errors.append(str(e))

    # ── Process Local Collection ────────────────────────────
    if local_docs:
        parsed_docs = []
        for f in local_docs:
            doc = parse_local_file(f)
            if doc:
                parsed_docs.append(doc)
            else:
                skipped += 1
            processed += 1
            _ingest_progress["processed"] = processed

        if parsed_docs:
            try:
                nodes = chunk_documents(parsed_docs)
                total_chunks += len(nodes)
                ingest_nodes_to_collection(nodes, LOCAL_COLLECTION)
            except Exception as e:
                logger.error(f"Local ingestion failed: {e}")
                errors.append(str(e))

    _ingest_progress.update({"running": False, "done": True})

    try:
        refresh_local_stats()
    except Exception:
        pass

    return JsonResponse({
        "status": "ingested",
        "files_processed": processed - skipped,
        "files_skipped": skipped,
        "total_chunks": total_chunks,
        "errors": errors[:10],
    })

# --- Custom Multi-Collection Retriever ---
class MultiCollectionRetriever(BaseRetriever):
    def __init__(self, cloud_retriever, local_retriever):
        self.cloud_retriever = cloud_retriever
        self.local_retriever = local_retriever
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle):
        nodes = []
        if self.cloud_retriever:
            try:
                nodes.extend(self.cloud_retriever.retrieve(query_bundle))
            except Exception:
                pass
        if self.local_retriever:
            try:
                nodes.extend(self.local_retriever.retrieve(query_bundle))
            except Exception:
                pass
        return nodes

def search(request):
    try:
        payload = json.loads(request.body) if request.body else {}
    except ValueError:
        payload = {}
        
    query = payload.get("query", "").strip()
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    app_settings = load_app_settings()
    cloud_enabled = app_settings.get("cloud_enabled", True)
    local_enabled = app_settings.get("local_enabled", True)

    # 1. Deterministic Intent Routing
    intent = classify_intent(query)
    logger.info(f"Classified intent: {intent} for query: {query}")

    if intent == "GENERAL":
        answer_str = get_general_response(query)
        return JsonResponse({
            "query": query,
            "answer": answer_str,
            "answer_model": "LlamaIndex Classifier (General)",
            "answer_error": None,
            "results": [],
            "total": 0,
            "source": "conversational",
            "indexed": True,
            "settings": app_settings,
        })

    # 2. RAG Pathway (SEARCH)
    try:
        cloud_retriever = None
        local_retriever = None
        
        # Build individual hybrid retrievers if collections exist
        from api.services.rag.indexer import get_qdrant_client
        
        client = get_qdrant_client()
        embedder = get_embedder()

        if cloud_enabled and client.collection_exists(CLOUD_COLLECTION):
            idx = VectorStoreIndex.from_vector_store(get_vector_store(CLOUD_COLLECTION), embed_model=embedder)
            from api.services.rag.retrieval.hybrid import get_base_retriever
            base_ret = get_base_retriever(idx, top_k=20)
            cloud_retriever = base_ret

        if local_enabled and client.collection_exists(LOCAL_COLLECTION):
            idx = VectorStoreIndex.from_vector_store(get_vector_store(LOCAL_COLLECTION), embed_model=embedder)
            from api.services.rag.retrieval.hybrid import get_base_retriever
            base_ret = get_base_retriever(idx, top_k=20)
            local_retriever = base_ret

        multi_retriever = MultiCollectionRetriever(cloud_retriever, local_retriever)
        reranker = get_cross_encoder_reranker(top_n=5)
        
        engine = build_query_engine(multi_retriever, reranker)
        
        logger.info(f"Querying RAG engine: {query}")
        response = engine.query(query)
        
        # Parse Source Nodes for frontend
        hits = []
        seen_fids = set()
        
        for node in response.source_nodes:
            meta = node.node.metadata
            fid = meta.get("file_id") or meta.get("file_name", "unknown")
            if fid not in seen_fids:
                seen_fids.add(fid)
                score = round(node.score if node.score else 0.0, 3)
                source_type = meta.get("source", "google")
                hits.append({
                    "id": fid,
                    "name": meta.get("file_name", "Unknown"),
                    "mimeType": meta.get("mime_type", ""),
                    "webViewLink": meta.get("web_view_link", ""),
                    "modifiedTime": meta.get("modified_time", ""),
                    "snippet": node.node.get_content()[:320].strip(),
                    "score": score,
                    "source": source_type,
                    "localPath": meta.get("local_path", ""),
                    "relevance_hint": f"{'Cloud Match' if source_type == 'cloud' else 'Local Match'} · Reranked Score: {score}",
                })

        answer_str = str(response).strip()
        if not answer_str or answer_str == "None":
            answer_str = "I could not find relevant information regarding this in the indexed files."

        return JsonResponse({
            "query": query,
            "answer": answer_str,
            "answer_model": "LlamaIndex Engine",
            "answer_error": None,
            "results": hits,
            "total": len(hits),
            "source": "semantic_multi",
            "indexed": True,
            "settings": app_settings,
        })
        
    except Exception as exc:
        import traceback
        logger.error("New LlamaIndex Search error: %s\n%s", exc, traceback.format_exc())
        return JsonResponse({
            "query": query,
            "answer": None,
            "answer_error": f"LlamaIndex engine failed: {exc}",
            "answer_model": None,
            "results": [],
            "total": 0,
            "source": "error",
            "indexed": True,
            "settings": app_settings,
        })

# LLM Status endpoint remains the same since it's just Ollama generic checks
def llm_status(request):
    try:
        from api.services.llm_client import ollama_list_models
        from api.services.config import load_llm_config
        cfg = load_llm_config()
        models = ollama_list_models(cfg.get("base_url", "http://localhost:11434"))
        return JsonResponse({
            "reachable": True,
            "provider": cfg.get("provider", "ollama"),
            "current_model": cfg.get("model", ""),
            "base_url": cfg.get("base_url", ""),
            "available_models": models
        })
    except Exception:
        return JsonResponse({"reachable": False})

def save_llm_config(request):
    try:
        payload = json.loads(request.body)
        from api.services.config import load_llm_config, save_llm_config as save_cfg
        cfg = load_llm_config()
        if "base_url" in payload:
            cfg["base_url"] = payload["base_url"]
        if "model" in payload:
            cfg["model"] = payload["model"]
        if "provider" in payload:
            cfg["provider"] = payload["provider"]
        save_cfg(cfg)
        return JsonResponse({"status": "saved"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
