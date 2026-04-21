import os
import pathlib
import time
import json
import logging
from django.http import JsonResponse

from api.services.config import local_files_meta, local_files_meta_save, LOCAL_FILES_PATH, LOCAL_ALLOWED_EXTENSIONS, load_app_settings

# --- NEW RAG ARCHITECTURE IMPORTS ---
from api.services.rag.indexer import get_qdrant_client, LOCAL_COLLECTION
from api.services.rag.ingestion.parsers import parse_local_file
from api.services.rag.ingestion.chunking import chunk_documents
from api.services.rag.ingestion.pipeline import ingest_nodes_to_collection

logger = logging.getLogger(__name__)

def get_tree(request):
    settings = load_app_settings().get("sources", {})
    root_path = settings.get("local_root_path")
    if not root_path or not os.path.exists(root_path):
        return JsonResponse({"error": "Local root path not set or invalid"}, status=400)

    def build_tree(current_path, depth=0):
        if depth > 5: return None
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

    client = get_qdrant_client()
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
        file_id = f"local__{dest.resolve()}"

        file_info = {
            "id": file_id,
            "name": dest.name,
            "local_path": str(dest.resolve()),
            "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(dest))),
        }

        doc = parse_local_file(file_info)
        if not doc:
            dest.unlink(missing_ok=True)
            results.append({"name": original_name, "status": "error", "reason": "Could not extract text"})
            continue
            
        nodes = chunk_documents([doc])
        if not nodes:
            dest.unlink(missing_ok=True)
            results.append({"name": original_name, "status": "error", "reason": "Text too short to chunk"})
            continue

        # We delete old versions of this file if they existed in Qdrant Local Collection
        try:
            if client.collection_exists(LOCAL_COLLECTION):
                from qdrant_client.http import models
                client.delete(
                    collection_name=LOCAL_COLLECTION,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=[
                                models.FieldCondition(
                                    key="file_name",
                                    match=models.MatchValue(value=dest.name)
                                )
                            ]
                        )
                    )
                )
        except Exception as e:
            logger.warning(f"Error deleting old qdrant points: {e}")

        # Inject into Qdrant Local
        ingest_nodes_to_collection(nodes, LOCAL_COLLECTION)

        file_meta = {
            "id": file_id,
            "name": dest.name,
            "original_name": original_name,
            "size": size,
            "chunks": len(nodes),
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ext": ext,
        }
        meta_list = [m for m in meta_list if m.get("name") != dest.name] # prevent dupes by name
        meta_list.append(file_meta)
        results.append({"name": original_name, "status": "indexed", "chunks": len(nodes)})

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

    # In our old logic, file_id was sometimes just 'local__filename'
    file_name = file_id.split("local__")[-1]
    
    # We attempt to find the file
    found_dest = None
    for p in LOCAL_FILES_PATH.iterdir():
        if p.name == file_name or str(p.resolve()) == file_name:
            found_dest = p
            break
            
    if not found_dest:
        dest = LOCAL_FILES_PATH / file_name
    else:
        dest = found_dest

    # Delete from Qdrant Local Collection via file_name filter
    try:
        client = get_qdrant_client()
        if client.collection_exists(LOCAL_COLLECTION):
             from qdrant_client.http import models
             client.delete(
                collection_name=LOCAL_COLLECTION,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="file_name",
                                match=models.MatchValue(value=dest.name)
                            )
                        ]
                    )
                )
             )
    except Exception as exc:
        logger.warning(f"Qdrant delete error for {dest.name}: {exc}")

    if dest.exists():
        dest.unlink(missing_ok=True)

    meta_list = local_files_meta()
    meta_list = [m for m in meta_list if m.get("id") != file_id and m.get("name") != dest.name]
    local_files_meta_save(meta_list)

    return JsonResponse({"status": "deleted"})
