import os
import pathlib
import time
import logging
from django.http import JsonResponse

from api.services.config import local_files_meta, local_files_meta_save, LOCAL_FILES_PATH, LOCAL_ALLOWED_EXTENSIONS, load_app_settings
from api.services.text_extraction import extract_text_from_local
from api.services.chunking import chunk_text
from api.services.chromadb_store import get_collection

logger = logging.getLogger(__name__)

def get_tree(request):
    settings = load_app_settings()
    root_path = settings.get("local_root_path")
    if not root_path or not os.path.exists(root_path):
        return JsonResponse({"error": "Local root path not set or invalid"}, status=400)

    def build_tree(current_path, depth=0):
        if depth > 5: # Reasonable limit for initial release
             return None
        
        name = os.path.basename(current_path) or current_path
        tree = {"name": name, "path": current_path, "type": "dir", "children": []}
        
        try:
            with os.scandir(current_path) as entries:
                for entry in entries:
                    if entry.is_dir():
                        subdir = build_tree(entry.path, depth + 1)
                        if subdir: tree["children"].append(subdir)
                    else:
                        ext = pathlib.Path(entry.name).suffix.lower()
                        if ext in LOCAL_ALLOWED_EXTENSIONS:
                            tree["children"].append({
                                "name": entry.name,
                                "path": entry.path,
                                "type": "file",
                                "size": entry.stat().st_size
                            })
        except (PermissionError, OSError):
            pass
            
        return tree

    try:
        tree_data = build_tree(root_path)
        return JsonResponse(tree_data)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def list_files(request):
    return JsonResponse({"files": local_files_meta()})

def upload(request):
    uploaded = request.FILES.getlist("files")
    if not uploaded:
        return JsonResponse({"error": "No files provided"}, status=400)

    col = get_collection()
    meta_list = local_files_meta()
    results = []

    for f in uploaded:
        original_name = f.name or "upload"
        ext = pathlib.Path(original_name).suffix.lower()
        if ext not in LOCAL_ALLOWED_EXTENSIONS:
            results.append({"name": original_name, "status": "skipped", "reason": f"Unsupported type {ext}"})
            continue

        safe_name = pathlib.Path(original_name).name
        dest = LOCAL_FILES_PATH / safe_name
        counter = 1
        while dest.exists():
            stem = pathlib.Path(safe_name).stem
            dest = LOCAL_FILES_PATH / f"{stem}_{counter}{ext}"
            counter += 1

        with open(dest, "wb+") as dest_file:
            for chunk in f.chunks():
                dest_file.write(chunk)
                
        size = dest.stat().st_size

        text = extract_text_from_local(dest)
        if not text or not text.strip():
            dest.unlink(missing_ok=True)
            results.append({"name": original_name, "status": "error", "reason": "Could not extract text"})
            continue

        chunks = chunk_text(text)
        if not chunks:
            dest.unlink(missing_ok=True)
            results.append({"name": original_name, "status": "error", "reason": "Text too short to chunk"})
            continue

        file_id = "local__" + dest.name
        try:
            existing = col.get(where={"source": "local", "file_name": dest.name})
            if existing and existing.get("ids"):
                col.delete(ids=existing["ids"])
        except Exception:
            pass

        ids = [f"{file_id}__chunk__{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": "local", "file_name": dest.name, "file_path": str(dest), "chunk_index": i}
            for i in range(len(chunks))
        ]
        col.upsert(ids=ids, documents=chunks, metadatas=metadatas)

        file_meta = {
            "id": file_id,
            "name": dest.name,
            "original_name": original_name,
            "size": size,
            "chunks": len(chunks),
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ext": ext,
        }
        meta_list = [m for m in meta_list if m.get("id") != file_id]
        meta_list.append(file_meta)
        results.append({"name": original_name, "status": "indexed", "chunks": len(chunks)})

    local_files_meta_save(meta_list)
    return JsonResponse({"results": results, "total_files": len([r for r in results if r["status"] == "indexed"])})

def delete(request):
    try:
        body = json.loads(request.body) if request.body else {}
    except ValueError:
        body = {}
        
    file_id = body.get("file_id", "")
    if not file_id or not file_id.startswith("local__"):
        return JsonResponse({"error": "Invalid file_id"}, status=400)

    file_name = file_id.replace("local__", "", 1)
    dest = LOCAL_FILES_PATH / file_name

    try:
        col = get_collection()
        existing = col.get(where={"source": "local", "file_name": file_name})
        if existing and existing.get("ids"):
            col.delete(ids=existing["ids"])
    except Exception as exc:
        logger.warning("ChromaDB delete error for %s: %s", file_name, exc)

    if dest.exists():
        dest.unlink()

    meta_list = [m for m in local_files_meta() if m.get("id") != file_id]
    local_files_meta_save(meta_list)

    return JsonResponse({"status": "deleted", "file_id": file_id})
