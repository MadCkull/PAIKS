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

logger = logging.getLogger(__name__)

def folders(request):
    creds = get_creds()
    if not creds:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    try:
        service = drive_service(creds)
        folders_list = []
        page_token = None
        while True:
            params = {
                "pageSize": 100,
                "fields": "nextPageToken, files(id, name, modifiedTime)",
                "q": "mimeType = 'application/vnd.google-apps.folder' and trashed = false",
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

def files(request):
    creds = get_creds()
    if not creds:
        return JsonResponse({"error": "Not authenticated", "files": []}, status=200)

    try:
        page_token = request.GET.get("pageToken")
        page_size = int(request.GET.get("pageSize", 20))
        name_query = request.GET.get("q", "")

        folder_cfg = load_folder_config()
        service = drive_service(creds)

        conditions = ["trashed = false", MIME_FILTER]
        if folder_cfg and folder_cfg.get("folder_id"):
            conditions.append(f"'{folder_cfg['folder_id']}' in parents")
        if name_query:
            escaped = name_query.replace("'", "\\'")
            conditions.append(f"name contains '{escaped}'")

        params = {
            "pageSize": page_size,
            "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, size, iconLink, webViewLink, thumbnailLink)",
            "orderBy": "modifiedTime desc",
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
        return JsonResponse({"error": "Not authenticated — skipping cloud sync"}, status=200)

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
    """Lightweight stats endpoint — reads from caches only, no network or filesystem scans."""
    creds = get_creds()
    cache = load_cache()
    app_settings = load_app_settings()

    # ── CLOUD STATS (from sync cache) ────────────────────────
    cloud_files = cache.get("files", [])
    cloud_total = len(cloud_files)
    cloud_size = 0
    for f in cloud_files:
        s = f.get("size")
        if s and str(s).isdigit():
            cloud_size += int(s)

    file_types = {}
    for f in cloud_files:
        mime = f.get("mimeType", "unknown")
        ext = mime.split("/")[-1].split(".")[-1]
        file_types[ext] = file_types.get(ext, 0) + 1

    # ── LOCAL STATS (from cache file, NOT live scan) ─────────
    local_stats = load_local_stats_cache()
    local_total = local_stats.get("total", 0)
    local_size = local_stats.get("size", 0)
    for ext, count in local_stats.get("file_types", {}).items():
        file_types[ext] = file_types.get(ext, 0) + count

    return JsonResponse({
        "authenticated": creds is not None,
        "cloud_enabled": app_settings.get("cloud_enabled", True),
        "local_enabled": app_settings.get("local_enabled", False),
        "cloud_total": cloud_total,
        "local_total": local_total,
        "documents_total": cloud_total + local_total,
        "total_size_bytes": cloud_size + local_size,
        "synced_at": cache.get("synced_at", "Not synced yet"),
        "file_types": file_types,
        "folder": load_folder_config(),
        "local_root": app_settings.get("local_root_path")
    })
