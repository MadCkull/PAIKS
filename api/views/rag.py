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
from api.services.rag.generation.engine import build_query_engine
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

    history = payload.get("history", [])  # optional conversation context

    app_settings = load_app_settings()
    cloud_enabled = app_settings.get("cloud_enabled", True)
    local_enabled = app_settings.get("local_enabled", True)

    # 1. Query Intelligence Layer
    from api.services.rag.retrieval.query_rewriter import (
        rewrite_query, detect_filename_query, get_known_files_from_qdrant,
    )

    # Check if user is asking about a specific file
    known_files = get_known_files_from_qdrant()
    file_match = detect_filename_query(query, known_files)

    # Rewrite query for better retrieval (unless it's a filename-specific query)
    retrieval_query = query
    if not file_match:
        retrieval_query = rewrite_query(query, history if history else None)

    # 2. Always-Retrieve RAG Pathway (no routing decision)
    try:
        from api.services.rag.indexer import get_qdrant_client
        
        client = get_qdrant_client()
        embedder = get_embedder()

        # If a specific file was detected, do metadata-filtered retrieval
        if file_match:
            logger.info(f"File-specific retrieval for: {file_match.get('file_name')}")
            response = _file_specific_query(
                query, file_match, client, embedder, cloud_enabled, local_enabled
            )
        else:
            # Normal multi-collection retrieval with rewritten query
            cloud_retriever = None
            local_retriever = None

            if cloud_enabled and client.collection_exists(CLOUD_COLLECTION):
                idx = VectorStoreIndex.from_vector_store(get_vector_store(CLOUD_COLLECTION), embed_model=embedder)
                base_ret = get_base_retriever(idx, top_k=20)
                cloud_retriever = base_ret

            if local_enabled and client.collection_exists(LOCAL_COLLECTION):
                idx = VectorStoreIndex.from_vector_store(get_vector_store(LOCAL_COLLECTION), embed_model=embedder)
                base_ret = get_base_retriever(idx, top_k=20)
                local_retriever = base_ret

            multi_retriever = MultiCollectionRetriever(cloud_retriever, local_retriever)
            reranker = get_cross_encoder_reranker(top_n=5)
            engine = build_query_engine(multi_retriever, reranker)
            
            logger.info(f"Querying RAG engine with: {retrieval_query}")
            response = engine.query(retrieval_query)
        
        # Parse Source Nodes for frontend
        hits = []
        seen_fids = set()
        
        for node in response.source_nodes:
            meta = node.node.metadata
            fid = meta.get("file_id") or meta.get("file_name", "unknown")
            score = round(node.score if node.score else 0.0, 3)
            
            logger.info(f"RAG Hit: {meta.get('file_name')} | Section: {meta.get('section_header', '')} | Score: {score}")

            if fid not in seen_fids:
                if score < 0.05:
                    continue
                
                seen_fids.add(fid)
                source_type = meta.get("source", "google")
                hits.append({
                    "id": fid,
                    "name": meta.get("file_name", "Unknown"),
                    "mimeType": meta.get("mime_type", ""),
                    "webViewLink": meta.get("web_view_link", ""),
                    "modifiedTime": meta.get("modified_time", ""),
                    "snippet": node.node.get_content()[:800].strip(),
                    "score": score,
                    "source": source_type,
                    "localPath": meta.get("local_path", ""),
                    "section": meta.get("section_header", ""),
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


def _file_specific_query(query, file_match, client, embedder, cloud_enabled, local_enabled):
    """Handle queries about a specific file — fetch all its chunks + summary
    and run the query engine over just that file's content."""
    file_id = file_match["file_id"]
    collection = file_match["collection"]
    
    # Build a retriever for just this collection
    idx = VectorStoreIndex.from_vector_store(
        get_vector_store(collection), embed_model=embedder
    )
    base_ret = get_base_retriever(idx, top_k=30)
    reranker = get_cross_encoder_reranker(top_n=8)
    engine = build_query_engine(base_ret, reranker)
    
    # Query with the original query (not rewritten, since it's file-targeted)
    return engine.query(query)

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

# --- DEBUG / INSPECTOR ENDPOINTS ---

def debug_indices(request):
    """
    Returns a grouped, file-centric view of ALL raw data in Qdrant collections.
    Calculates metrics, identifies empty/fragmented files, and reports summary status.
    """
    import json
    from api.services.rag.indexer import get_qdrant_client, LOCAL_COLLECTION, CLOUD_COLLECTION
    client = get_qdrant_client()
    
    # Structure: { file_id: { name, source, file_id, chunks: [], has_summary, summary_text } }
    grouped_data = {}
    
    def fetch_all_from_collection(col_name):
        if not client.collection_exists(col_name):
            return
            
        next_offset = None
        while True:
            points, next_offset = client.scroll(
                collection_name=col_name,
                limit=100,
                offset=next_offset,
                with_payload=True,
                with_vectors=False
            )
            
            for p in points:
                payload = p.payload
                fid = payload.get("file_id") or "unknown"
                is_summary = payload.get("is_summary", False)
                
                if fid not in grouped_data:
                    grouped_data[fid] = {
                        "file_id": fid,
                        "name": payload.get("file_name", "Unknown File"),
                        "source": col_name.split("_")[1],
                        "collection": col_name,
                        "modified": payload.get("modified_time", ""),
                        "chunks": [],
                        "has_summary": False,
                        "summary_text": None,
                    }
                
                # Extract clean text
                text = payload.get("text") or payload.get("content")
                if not text and "_node_content" in payload:
                    try:
                        node_data = json.loads(payload["_node_content"])
                        text = node_data.get("text")
                    except: pass
                
                if is_summary:
                    grouped_data[fid]["has_summary"] = True
                    grouped_data[fid]["summary_text"] = text or ""
                else:
                    grouped_data[fid]["chunks"].append({
                        "id": p.id,
                        "text": text or "[Empty snippet]",
                        "section": payload.get("section_header", ""),
                    })
                
            if next_offset is None:
                break

    fetch_all_from_collection(LOCAL_COLLECTION)
    fetch_all_from_collection(CLOUD_COLLECTION)
    
    sort_priority = {"local": 0, "cloud": 1}
    result_list = sorted(
        grouped_data.values(), 
        key=lambda x: (sort_priority.get(x["source"], 99), x["name"].lower())
    )
    
    metrics = {
        "total_files": len(result_list),
        "local_count": sum(1 for x in result_list if x["source"] == "local"),
        "cloud_count": sum(1 for x in result_list if x["source"] == "cloud"),
        "total_chunks": sum(len(x["chunks"]) for x in result_list),
        "summaries_generated": sum(1 for x in result_list if x["has_summary"]),
    }
            
    return JsonResponse({
        "files": result_list,
        "metrics": metrics
    })

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


# --- SUMMARY GENERATION ENDPOINTS ---

def generate_summary(request):
    """Generate a document summary for a specific file_id.
    POST body: { "file_id": "...", "collection": "paiks_local_index" }
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    file_id = payload.get("file_id", "").strip()
    collection = payload.get("collection", "").strip()

    if not file_id or not collection:
        return JsonResponse({"error": "file_id and collection are required"}, status=400)

    from api.services.rag.indexer import get_qdrant_client
    from api.services.rag.ingestion.summary import generate_summary_text, store_summary_node

    client = get_qdrant_client()
    if not client.collection_exists(collection):
        return JsonResponse({"error": f"Collection '{collection}' not found"}, status=404)

    # Fetch all regular chunks for this file
    chunk_texts = []
    file_name = "Unknown"
    source_type = "local"

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        next_offset = None
        while True:
            points, next_offset = client.scroll(
                collection_name=collection,
                scroll_filter=Filter(must=[
                    FieldCondition(key="file_id", match=MatchValue(value=file_id)),
                ]),
                limit=100,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                pl = p.payload
                if pl.get("is_summary", False):
                    continue
                file_name = pl.get("file_name", file_name)
                source_type = pl.get("source", source_type)
                text = pl.get("text") or pl.get("content")
                if not text and "_node_content" in pl:
                    try:
                        import json as _json
                        nd = _json.loads(pl["_node_content"])
                        text = nd.get("text")
                    except Exception:
                        pass
                if text:
                    chunk_texts.append(text)
            if next_offset is None:
                break
    except Exception as e:
        return JsonResponse({"error": f"Failed to read chunks: {e}"}, status=500)

    if not chunk_texts:
        return JsonResponse({"error": "No chunks found for this file"}, status=404)

    # Generate summary via LLM
    try:
        summary = generate_summary_text(chunk_texts, file_name)
    except Exception as e:
        logger.error(f"Summary generation failed for {file_name}: {e}")
        return JsonResponse({"error": f"LLM generation failed: {e}"}, status=500)

    # Store in Qdrant
    try:
        store_summary_node(
            summary_text=summary,
            file_id=file_id,
            filename=file_name,
            source=source_type,
            collection_name=collection,
        )
    except Exception as e:
        logger.error(f"Summary storage failed for {file_name}: {e}")
        return JsonResponse({"error": f"Storage failed: {e}"}, status=500)

    return JsonResponse({
        "status": "generated",
        "file_id": file_id,
        "file_name": file_name,
        "summary": summary,
    })
