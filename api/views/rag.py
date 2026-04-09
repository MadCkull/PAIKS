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
    from api.services.rag.tracer import PipelineTracer

    try:
        payload = json.loads(request.body) if request.body else {}
    except ValueError:
        payload = {}
        
    query = payload.get("query", "").strip()
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    history = payload.get("history", [])  # optional conversation context

    # ── Start pipeline trace ──
    tracer = PipelineTracer(query)
    tracer.log_section("1. RAW USER QUERY", {"query": query})
    tracer.log_section("2. CONVERSATION HISTORY (from frontend)", history if history else "(none sent)")

    app_settings = load_app_settings()
    cloud_enabled = app_settings.get("cloud_enabled", True)
    local_enabled = app_settings.get("local_enabled", True)
    tracer.log_section("3. APP SETTINGS", {
        "cloud_enabled": cloud_enabled,
        "local_enabled": local_enabled,
    })

    # 1. Query Intelligence Layer (filename detection only — rewriter disabled)
    from api.services.rag.retrieval.query_rewriter import (
        detect_filename_query, get_known_files_from_qdrant,
    )

    known_files = get_known_files_from_qdrant()
    tracer.log_section("4. KNOWN FILES IN QDRANT", [
        {"file_id": f["file_id"], "file_name": f["file_name"], "source": f["source"], "collection": f["collection"]}
        for f in known_files
    ])

    file_match = detect_filename_query(query, known_files)
    tracer.log_section("5. FILENAME DETECTION", file_match if file_match else "(no filename match)")

    # Use original query directly — LLM rewriter was destroying queries
    retrieval_query = query
    tracer.log_section("6. QUERY FOR RETRIEVAL", {
        "retrieval_query": retrieval_query,
        "note": "Using original query (rewriter disabled)",
    })

    # 2. Always-Retrieve RAG Pathway
    try:
        from api.services.rag.indexer import get_qdrant_client
        from api.services.rag.generation.prompts import build_query_with_history
        
        client = get_qdrant_client()
        embedder = get_embedder()

        # Build the history-aware query string for the LLM
        llm_query = build_query_with_history(query, history if history else None)
        tracer.log_section("6B. LLM SYNTHESIS QUERY", {"llm_query": llm_query})

        tracer.log_section("7. EMBEDDING MODEL", {
            "model_name": str(getattr(embedder, 'model_name', 'unknown')),
            "base_url": str(getattr(embedder, 'base_url', 'unknown')),
        })

        if file_match:
            logger.info(f"File-specific retrieval for: {file_match.get('file_name')}")
            tracer.log_text("8. RETRIEVAL MODE", f"FILE-SPECIFIC: {file_match.get('file_name')} (collection: {file_match.get('collection')})")
            response = _file_specific_query(
                query, llm_query, file_match, client, embedder, cloud_enabled, local_enabled
            )
        else:
            cloud_retriever = None
            local_retriever = None

            collections_used = []
            if cloud_enabled and client.collection_exists(CLOUD_COLLECTION):
                idx = VectorStoreIndex.from_vector_store(get_vector_store(CLOUD_COLLECTION), embed_model=embedder)
                base_ret = get_base_retriever(idx, top_k=20)
                cloud_retriever = base_ret
                collections_used.append(CLOUD_COLLECTION)

            if local_enabled and client.collection_exists(LOCAL_COLLECTION):
                idx = VectorStoreIndex.from_vector_store(get_vector_store(LOCAL_COLLECTION), embed_model=embedder)
                base_ret = get_base_retriever(idx, top_k=20)
                local_retriever = base_ret
                collections_used.append(LOCAL_COLLECTION)

            tracer.log_section("8. RETRIEVAL MODE", {
                "mode": "MULTI-COLLECTION",
                "collections_used": collections_used,
                "retriever_top_k": 20,
                "reranker_top_n": 5,
                "query_sent_to_retriever": retrieval_query,
            })

            multi_retriever = MultiCollectionRetriever(cloud_retriever, local_retriever)
            reranker = get_cross_encoder_reranker(top_n=5)
            engine = build_query_engine(multi_retriever, reranker)
            
            from llama_index.core import QueryBundle
            
            logger.info(f"Retrieving chunks for: {retrieval_query}")
            nodes = engine.retrieve(QueryBundle(retrieval_query))
            
            # Filter garbage chunks so the LLM isn't confused by irrelevant context
            filtered_nodes = [n for n in nodes if n.score is None or n.score >= 0.05]
            
            # If all chunks were garbage, LlamaIndex natively short-circuits and refuses to call the LLM, returning "Empty Response".
            # We inject a dummy empty node with score=0.0 to force LlamaIndex to query the LLM using just the history block! 
            # The score=0.0 ensures it gets cleanly excluded from the frontend hits below.
            if not filtered_nodes:
                from llama_index.core.schema import NodeWithScore, TextNode
                dummy_node = TextNode(text="")
                dummy_node.metadata = {"file_id": "dummy", "file_name": "dummy"}
                filtered_nodes = [NodeWithScore(node=dummy_node, score=0.0)]
            
            logger.info(f"Synthesizing answer with history injected context over {len(filtered_nodes)} relevant nodes...")
            response = engine.synthesize(QueryBundle(llm_query), filtered_nodes)
        
        # ── Log ALL raw source nodes from the response ──
        tracer.log_nodes("9. SOURCE NODES (after reranking)", response.source_nodes)

        # ── Log the exact context the LLM received ──
        context_texts = []
        for node in response.source_nodes:
            try:
                ctx = node.node.get_content()
                meta = node.node.metadata
                context_texts.append({
                    "file": meta.get("file_name", "?"),
                    "section": meta.get("section_header", ""),
                    "score": round(node.score, 4) if node.score else None,
                    "text": ctx,
                })
            except Exception:
                pass
        tracer.log_section("10. CONTEXT ASSEMBLED FOR LLM", context_texts)

        # ── Log the raw LLM response ──
        raw_response = str(response)
        tracer.log_text("11. RAW LLM RESPONSE", raw_response)

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
                    tracer.log_text("12. FILTERED OUT (score < 0.05)", f"{meta.get('file_name')} — score: {score}")
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

        tracer.log_section("13. FINAL RESPONSE TO FRONTEND", {
            "answer": answer_str,
            "hits_count": len(hits),
            "hits": [{"name": h["name"], "score": h["score"], "section": h.get("section", "")} for h in hits],
        })
        tracer.flush()

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
        tb = traceback.format_exc()
        logger.error("New LlamaIndex Search error: %s\n%s", exc, tb)
        tracer.log_text("ERROR — PIPELINE CRASHED", f"{exc}\n\n{tb}")
        tracer.flush()
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


def _file_specific_query(query, llm_query, file_match, client, embedder, cloud_enabled, local_enabled):
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
    from llama_index.core import QueryBundle
    
    # Retrieve with the original query, synthesize with the history-aware query
    nodes = engine.retrieve(QueryBundle(query))
    
    # Filter garbage chunks to prevent conversational hallucinations
    filtered_nodes = [n for n in nodes if n.score is None or n.score >= 0.05]
    
    if not filtered_nodes:
        from llama_index.core.schema import NodeWithScore, TextNode
        dummy_node = TextNode(text="")
        dummy_node.metadata = {"file_id": "dummy", "file_name": "dummy"}
        filtered_nodes = [NodeWithScore(node=dummy_node, score=0.0)]
    
    # Note: LlamaIndex response object usually carries source_nodes, so we overwrite it back to `nodes`
    # or pass `filtered_nodes` directly to synthesize. But `tracer.log_nodes` reads from `response.source_nodes`
    # and if we pass filtered_nodes to synthesize, `response.source_nodes` will correctly reflect only the nodes we actually sent!
    return engine.synthesize(QueryBundle(llm_query), filtered_nodes)

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
