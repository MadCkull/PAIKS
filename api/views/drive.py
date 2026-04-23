import json
import logging
from datetime import datetime, timezone
from django.http import JsonResponse

from api.services.google_auth import get_creds
from api.services.google_drive import drive_service, MIME_FILTER
from api.services.config import (
    load_folder_config, save_folder_config, FOLDER_CONFIG_PATH, SYNC_CACHE_PATH,
    load_cache, save_cache, load_app_settings, load_local_stats_cache, save_local_stats_cache
)
import os
import pathlib
from django.db.models import Count, Sum

logger = logging.getLogger(__name__)

def folders(request):
    creds = get_creds()
    if not creds:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    parent_id = request.GET.get("parent_id", None)
    
    if not parent_id:
        current = load_folder_config()
        return JsonResponse({
            "folders": [
                {"id": "root", "name": "My Drive", "type": "root"},
                {"id": "shared", "name": "Shared with me", "type": "shared"}
            ],
            "current_folder": current,
            "parent_id": None
        })

    try:
        service = drive_service(creds)
        folders_list = []
        page_token = None

        if parent_id == "shared":
            base_q = "sharedWithMe = true and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        else:
            base_q = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

        while True:
            params = {
                "pageSize": 100,
                "fields": "nextPageToken, files(id, name, mimeType)",
                "q": base_q,
                "orderBy": "name",
            }
            if page_token:
                params["pageToken"] = page_token
            results = service.files().list(**params).execute()
            folders_list.extend(results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break

        current = load_folder_config()
        return JsonResponse({
            "folders": folders_list,
            "current_folder": current,
            "parent_id": parent_id,
        })
    except Exception as e:
        logger.error("drive_list_folders error: %s", str(e))
        return JsonResponse({"error": str(e)}, status=500)


def set_folder(request):
    try:
        payload = json.loads(request.body) if request.body else {}
    except ValueError:
        payload = {}

    folder_id = payload.get("folder_id", "").strip()
    folder_name = payload.get("folder_name", "").strip()

    if folder_id:
        save_folder_config(folder_id, folder_name)
        if SYNC_CACHE_PATH.exists():
            SYNC_CACHE_PATH.unlink()
        return JsonResponse({"status": "saved", "folder_id": folder_id, "folder_name": folder_name})
    else:
        if FOLDER_CONFIG_PATH.exists():
            FOLDER_CONFIG_PATH.unlink()
        if SYNC_CACHE_PATH.exists():
            SYNC_CACHE_PATH.unlink()
        return JsonResponse({"status": "cleared"})

def folder_config(request):
    return JsonResponse(load_folder_config() or {})

def _fetch_drive_files_recursive(service, parent_id, collected_files=None, depth=0, max_depth=3):
    if collected_files is None:
        collected_files = []
    if depth > max_depth:
        return collected_files

    page_token = None
    if parent_id == "shared":
        base_q = f"sharedWithMe = true and trashed = false and ({MIME_FILTER} or mimeType = 'application/vnd.google-apps.folder')"
    else:
        base_q = f"'{parent_id}' in parents and trashed = false and ({MIME_FILTER} or mimeType = 'application/vnd.google-apps.folder')"

    try:
        while True:
            results = service.files().list(
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType)",
                q=base_q,
            ).execute()
            
            for f in results.get("files", []):
                if f.get("mimeType") == "application/vnd.google-apps.folder":
                    _fetch_drive_files_recursive(service, f.get("id"), collected_files, depth + 1, max_depth)
                else:
                    collected_files.append({
                        "id": f"cloud__{f['id']}",
                        "name": f.get("name")
                    })
            
            page_token = results.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        logger.error(f"Recursive drive fetch error: {e}")
        
    return collected_files

def selection(request):
    try:
        payload = json.loads(request.body)
        file_ids = payload.get("file_ids", []) # explicit file IDs
        folder_ids = payload.get("folder_ids", []) # explicit folder IDs
        is_selected = payload.get("is_selected", True)
        
        from django.db import transaction
        from api.models import DocumentTrack, SyncJob
        from api.services.sync_manager import _compute_and_broadcast_health
        from api.services.sync_manager import logger as sync_logger
        
        creds = get_creds()
        service = drive_service(creds) if creds else None
        
        # Expand Google Drive folders recursively
        expanded_files = []
        if service and folder_ids:
            for fid in folder_ids:
                if fid.startswith("cloud__"):
                    raw_id = fid.replace("cloud__", "", 1)
                    found = _fetch_drive_files_recursive(service, raw_id)
                    expanded_files.extend(found)
                # Note: local folder expansion could be added here if needed

        # Prepare all files to process
        all_targets = []
        for fid in file_ids:
            all_targets.append({"id": fid, "name": None})
        all_targets.extend(expanded_files)

        # Build a fast mapping for Cloud File names
        cloud_name_map = {}
        try:
            from api.services.config import load_cache
            cache = load_cache()
            if cache and "files" in cache:
                for f in cache["files"]:
                    cloud_name_map[f"cloud__{f['id']}"] = f.get("name", f['id'])
        except Exception:
            pass

        processed = 0
        with transaction.atomic():
            for target in all_targets:
                fid = target["id"]
                target_name = target.get("name")
                
                # Determine correct fallback name based on source
                if not target_name:
                    if fid.startswith("cloud__"):
                        target_name = cloud_name_map.get(fid, fid.replace("cloud__", "", 1))
                    else:
                        import os
                        path_part = fid.replace("local__", "", 1)
                        target_name = os.path.basename(path_part) if path_part else fid

                doc, created = DocumentTrack.objects.get_or_create(
                    file_id=fid,
                    defaults={
                        "name": target_name,
                        "source": "cloud" if fid.startswith("cloud__") else "local",
                        "sync_status": "pending" if is_selected else "disabled",
                        "is_selected": is_selected
                    }
                )
                if not created:
                    # Heal random alphanumeric names from previous bugs dynamically
                    if doc.name != target_name and doc.source == "cloud" and not doc.name.endswith(('.txt', '.csv', '.doc', '.docx', '.pdf')):
                        doc.name = target_name

                    doc.is_selected = is_selected
                    if is_selected and doc.sync_status in ['disabled', 'error', 'pending']:
                        doc.sync_status = "pending"
                    elif not is_selected:
                        doc.sync_status = "disabled"
                    doc.save()
                
                if is_selected and doc.sync_status == "pending":
                    sync_logger.info(f"{doc.name} selected, queued for indexing.")
                    # Outbox record
                    SyncJob.objects.create(document=doc, action='index')
                elif not is_selected:
                    sync_logger.info(f"{doc.name} deselected, removing from knowledge base.")
                    # Outbox record
                    SyncJob.objects.create(document=doc, action='delete')
                
                processed += 1
        
        # If deselecting, immediately recompute health so badge updates
        if not is_selected:
            _compute_and_broadcast_health()
        
        # Push fresh stats to the frontend via SSE immediately
        from api.services.status_broadcaster import trigger_immediate_broadcast
        trigger_immediate_broadcast()
                
        return JsonResponse({"status": "updated", "count": processed})
    except Exception as e:
        logger.error(f"Selection update error: {e}")
        return JsonResponse({"error": str(e)}, status=400)

def selections(request):
    """Returns tracked file states for UI rendering."""
    try:
        from api.models import DocumentTrack
        selected_ids = list(DocumentTrack.objects.filter(is_selected=True).values_list('file_id', flat=True))
        disabled_ids = list(DocumentTrack.objects.filter(is_selected=False).values_list('file_id', flat=True))
        error_ids = list(DocumentTrack.objects.filter(sync_status="error").values_list('file_id', flat=True))
        synced_ids = list(DocumentTrack.objects.filter(sync_status="synced", is_selected=True).values_list('file_id', flat=True))
        return JsonResponse({
            "selected": selected_ids,
            "disabled": disabled_ids,
            "errors": error_ids,
            "synced": synced_ids
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def files(request):
    creds = get_creds()
    if not creds:
        return JsonResponse({"error": "Not authenticated", "files": []}, status=200)

    try:
        page_token = request.GET.get("pageToken")
        page_size = int(request.GET.get("pageSize", 100))
        name_query = request.GET.get("q", "")
        parent_id = request.GET.get("parent_id")

        folder_cfg = load_folder_config()
        service = drive_service(creds)

        target_parent = parent_id
        if not target_parent:
            target_parent = folder_cfg.get("folder_id") if folder_cfg else "root"

        conditions = ["trashed = false", f"({MIME_FILTER} or mimeType = 'application/vnd.google-apps.folder')"]
        
        if target_parent == "shared":
            conditions.append("sharedWithMe = true")
        elif target_parent:
            conditions.append(f"'{target_parent}' in parents")
            
        if name_query:
            escaped = name_query.replace("'", "\\'")
            conditions.append(f"name contains '{escaped}'")

        params = {
            "pageSize": page_size,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, iconLink, webViewLink, thumbnailLink)",
            "orderBy": "folder, name",
            "q": " and ".join(conditions),
        }
        if page_token:
            params["pageToken"] = page_token

        results = service.files().list(**params).execute()
        return JsonResponse({
            "files": results.get("files", []),
            "nextPageToken": results.get("nextPageToken"),
            "folder": folder_cfg,
        })
    except Exception as e:
        logger.error("drive_files error: %s", str(e))
        return JsonResponse({"error": str(e), "files": []}, status=200)

def sync(request):
    creds = get_creds()
    if not creds:
        return JsonResponse({"error": "Not authenticated  -  skipping cloud sync"}, status=200)

    folder_cfg = load_folder_config()
    try:
        service = drive_service(creds)
    except Exception as e:
        return JsonResponse({"error": f"Drive unavailable: {e}"}, status=200)

    all_files = []
    page_token = None

    base_q = f"trashed = false and {MIME_FILTER}"
    if folder_cfg and folder_cfg.get("folder_id"):
        base_q = f"'{folder_cfg['folder_id']}' in parents and trashed = false and {MIME_FILTER}"

    try:
        while True:
            params = {
                "pageSize": 100,
                "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, iconLink, webViewLink)",
                "q": base_q,
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                params["pageToken"] = page_token
            results = service.files().list(**params).execute()
            all_files.extend(results.get("files", []))
            page_token = results.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        logger.error("Drive sync failed: %s", e)
        return JsonResponse({"error": f"Cloud sync failed: {e}", "total": 0})

    cache_data = {
        "files": all_files,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "total": len(all_files),
        "folder": folder_cfg,
    }
    save_cache(cache_data)
    return JsonResponse({
        "status": "synced",
        "total": len(all_files),
        "synced_at": cache_data["synced_at"],
        "folder": folder_cfg,
    })

def refresh_local_stats():
    """Scan local root once and cache results. Called only during sync/ingest, NOT on every stats() call."""
    app_settings = load_app_settings()
    local_total = 0
    local_size = 0
    file_types = {}

    if app_settings.get("local_enabled") and app_settings.get("local_root_path"):
        root = pathlib.Path(app_settings["local_root_path"])
        if root.exists():
            try:
                for f in root.rglob("*"):
                    if f.is_file():
                        local_total += 1
                        try:
                            local_size += f.stat().st_size
                        except OSError:
                            pass
                        ext = f.suffix.lower().lstrip(".") or "other"
                        file_types[ext] = file_types.get(ext, 0) + 1
            except (PermissionError, OSError):
                pass

    stats_cache = {"total": local_total, "size": local_size, "file_types": file_types}
    save_local_stats_cache(stats_cache)
    return stats_cache

def stats(request):
    """Realtime stats endpoint  -  reads directly from DocumentTrack SQLite registry."""
    creds = get_creds()
    app_settings = load_app_settings()
    from api.models import DocumentTrack

    # Total files recognized by system (even if disabled)
    cloud_total = DocumentTrack.objects.filter(source="cloud").count()
    local_total = DocumentTrack.objects.filter(source="local").count()

    # Active indexed files
    indexed_total = DocumentTrack.objects.filter(sync_status="synced").count()
    syncing_total = DocumentTrack.objects.filter(sync_status="syncing").count()
    pending_total = DocumentTrack.objects.filter(sync_status="pending").count()
    disabled_total = DocumentTrack.objects.filter(sync_status="disabled").count()
    error_total = DocumentTrack.objects.filter(sync_status="error").count()

    src_cfg = app_settings.get("sources", {})
    return JsonResponse({
        "authenticated": creds is not None,
        "cloud_enabled": src_cfg.get("cloud_enabled", True),
        "local_enabled": src_cfg.get("local_enabled", False),
        "cloud_total": cloud_total,
        "local_total": local_total,
        "documents_total": cloud_total + local_total,
        "indexed_total": indexed_total,
        "syncing_total": syncing_total,
        "pending_total": pending_total,
        "disabled_total": disabled_total,
        "error_total": error_total,
        "folder": load_folder_config(),
        "local_root": src_cfg.get("local_root_path")
    })
