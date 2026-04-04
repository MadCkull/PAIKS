import json
import logging
from django.http import JsonResponse

from api.services.google_auth import get_creds
from api.services.google_drive import drive_service, MIME_FILTER
from api.services.config import load_cache, load_folder_config, load_llm_config, load_app_settings, LOCAL_ALLOWED_EXTENSIONS
from api.services.chromadb_store import get_collection
from api.services.text_extraction import extract_text_from_drive, extract_text_from_local
from api.services.chunking import chunk_text
from api.services.rag_pipeline import build_rag_prompt
from api.services.llm_client import call_local_llm
import os
import pathlib
import time
from api.views.drive import refresh_local_stats

logger = logging.getLogger(__name__)

_ingest_progress: dict = {"running": False, "processed": 0, "total": 0, "done": False, "error": None}

def status(request):
    try:
        col = get_collection()
        count = col.count()
        return JsonResponse({
            "indexed": count > 0,
            "total_chunks": count,
            "ingest_running": _ingest_progress["running"],
            "ingest_progress": _ingest_progress,
        })
    except Exception:
        return JsonResponse({"indexed": False, "total_chunks": 0, "ingest_running": False})

def ingest(request):
    global _ingest_progress

    if _ingest_progress.get("running"):
        return JsonResponse({"error": "Ingest already running. Check /api/rag/status for progress."}, status=409)

    app_settings = load_app_settings()
    cloud_enabled = app_settings.get("cloud_enabled", True)
    local_enabled = app_settings.get("local_enabled", True)
    local_root = app_settings.get("local_root_path")

    files_to_process = []

    # ── Gather Cloud Files ──────────────────────────────────
    if cloud_enabled:
        creds = get_creds()
        if creds:
            cache = load_cache()
            for f in cache.get("files", []):
                files_to_process.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "mime": f.get("mimeType"),
                    "source": "google",
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
                    files_to_process.append({
                        "id": f"local__{full_path}",
                        "name": filename,
                        "mime": "text/plain" if ext == ".txt" else "application/octet-stream", # simpler mime
                        "source": "local",
                        "local_path": full_path,
                        "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(full_path))),
                    })

    if not files_to_process:
        return JsonResponse({"error": "No files found to process. Check your data source settings and run sync."}, status=400)

    service = None
    if cloud_enabled:
        creds = get_creds()
        if creds: service = drive_service(creds)

    col = get_collection()
    _ingest_progress = {"running": True, "processed": 0, "total": len(files_to_process), "done": False, "error": None}

    processed, skipped, errors = 0, 0, []
    total_chunks = 0

    for f in files_to_process:
        fid = f["id"]
        fname = f["name"]
        mime = f["mime"]
        source = f["source"]

        try:
            if source == "google" and service:
                text = extract_text_from_drive(service, fid, mime)
            elif source == "local":
                text = extract_text_from_local(pathlib.Path(f["local_path"]))
            else:
                text = None
        except Exception as e:
            text = None
            logger.error("Extraction error for %s: %s", fname, e)

        if not text or not text.strip():
            skipped += 1
            _ingest_progress["processed"] += 1
            continue

        chunks = chunk_text(text)
        if not chunks:
            skipped += 1
            _ingest_progress["processed"] += 1
            continue

        ids = [f"{fid}__chunk__{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "file_id": fid,
                "file_name": fname,
                "mime_type": mime,
                "source": source,
                "web_view_link": f.get("link", ""),
                "local_path": f.get("local_path", ""),
                "modified_time": f.get("modified", ""),
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        try:
            col.upsert(ids=ids, documents=chunks, metadatas=metadatas)
            processed += 1
            total_chunks += len(chunks)
        except Exception as exc:
            errors.append({"file": fname, "error": str(exc)})
            logger.error("Chroma upsert failed for %s: %s", fname, exc)

        _ingest_progress["processed"] += 1

    _ingest_progress.update({"running": False, "done": True})

    # Update local stats cache so stats() endpoint is instant
    try:
        refresh_local_stats()
    except Exception:
        pass

    return JsonResponse({
        "status": "ingested",
        "files_processed": processed,
        "files_skipped": skipped,
        "total_chunks": total_chunks,
        "errors": errors[:10],
    })

def search(request):
    try:
        payload = json.loads(request.body) if request.body else {}
    except ValueError:
        payload = {}
        
    query = payload.get("query", "").strip()
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    app_settings = load_app_settings()
    llm_cfg = load_llm_config()

    try:
        col = get_collection()
        if col.count() > 0:
            n_retrieve = min(10, col.count())
            raw = col.query(
                query_texts=[query],
                n_results=n_retrieve,
                include=["documents", "metadatas", "distances"],
            )

            MAX_CONTEXT_CHARS = 2000
            llm_chunks: list[dict] = []
            total_chars = 0
            
            for doc, meta, dist in zip(
                raw["documents"][0][:5],
                raw["metadatas"][0][:5],
                raw["distances"][0][:5],
            ):
                if total_chars + len(doc) > MAX_CONTEXT_CHARS:
                    break
                llm_chunks.append({"name": meta["file_name"], "text": doc})
                total_chars += len(doc)

            seen = {}
            for doc, meta, dist in zip(
                raw["documents"][0],
                raw["metadatas"][0],
                raw["distances"][0],
            ):
                fid = meta.get("file_id") or meta.get("file_name", "unknown")
                score = round(1.0 - float(dist), 3)
                if fid not in seen or score > seen[fid]["score"]:
                    seen[fid] = {
                        "id": fid,
                        "name": meta.get("file_name", "Unknown"),
                        "mimeType": meta.get("mime_type", ""),
                        "webViewLink": meta.get("web_view_link", ""),
                        "modifiedTime": meta.get("modified_time", ""),
                        "snippet": doc[:320].strip(),
                        "score": score,
                        "source": meta.get("source", "google"),
                        "localPath": meta.get("local_path", ""),
                        "relevance_hint": f"{'Semantic match' if meta.get('source') == 'google' else 'Local match'} · {round(score * 100)}% relevance",
                    }

            hits = sorted(seen.values(), key=lambda x: x["score"], reverse=True)

            answer = None
            answer_model = None
            answer_error = None

            if llm_chunks:
                try:
                    prompt = build_rag_prompt(query, llm_chunks)
                    answer = call_local_llm(prompt, llm_cfg)
                    answer_model = llm_cfg.get("model")
                except Exception as llm_exc:
                    answer_error = str(llm_exc)
                    logger.warning("Local LLM call failed: %s", llm_exc)

            return JsonResponse({
                "query": query,
                "answer": answer,
                "answer_model": answer_model,
                "answer_error": answer_error,
                "results": hits,
                "total": len(hits),
                "source": "semantic",
                "indexed": True,
                "settings": app_settings,
            })
    except Exception as exc:
        import traceback
        logger.error("Semantic search error: %s\n%s", exc, traceback.format_exc())
        return JsonResponse({
            "query": query,
            "answer": None,
            "answer_error": f"Semantic search failed: {exc}",
            "answer_model": None,
            "results": [],
            "total": 0,
            "source": "error",
            "indexed": True,
            "settings": app_settings,
        })

    creds = get_creds()
    if creds:
        service = drive_service(creds)
        escaped = query.replace("'", "\\'")
        conditions = [f"name contains '{escaped}'", "trashed = false", MIME_FILTER]
        if folder_cfg and folder_cfg.get("folder_id"):
            conditions.append(f"'{folder_cfg['folder_id']}' in parents")
        try:
            res = (
                service.files()
                .list(
                    q=" and ".join(conditions),
                    pageSize=10,
                    fields="files(id, name, mimeType, modifiedTime, webViewLink, size)",
                    orderBy="modifiedTime desc",
                )
                .execute()
            )
            files = res.get("files", [])
        except Exception:
            files = []
    else:
        files = []

    if not files:
        cache = load_cache()
        words = [w.lower() for w in query.split() if w]
        scored = [
            (sum(1 for w in words if w in f.get("name", "").lower()), f)
            for f in cache.get("files", [])
        ]
        files = [f for score, f in sorted(scored, key=lambda x: x[0], reverse=True) if score > 0][:10]

    words = [w.lower() for w in query.split() if w]
    hits = [
        {
            "id": f.get("id"),
            "name": f.get("name", ""),
            "mimeType": f.get("mimeType", ""),
            "modifiedTime": f.get("modifiedTime", ""),
            "webViewLink": f.get("webViewLink", ""),
            "size": f.get("size"),
            "snippet": None,
            "score": None,
            "relevance_hint": (
                "Matched: " + ", ".join(w for w in words if w in f.get("name", "").lower())
                or "Drive full-text match"
            ),
        }
        for f in files
    ]

    return JsonResponse({
        "query": query,
        "answer": None,
        "answer_model": None,
        "answer_error": None,
        "results": hits,
        "total": len(hits),
        "source": "keyword",
        "indexed": False,
        "folder": folder_cfg,
    })
