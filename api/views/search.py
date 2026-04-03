import json
import logging
from django.http import JsonResponse

from api.services.google_auth import get_creds
from api.services.google_drive import drive_service, MIME_FILTER
from api.services.config import load_cache, load_folder_config

logger = logging.getLogger(__name__)

def search(request):
    try:
        payload = json.loads(request.body) if request.body else {}
    except ValueError:
        payload = {}
        
    query = payload.get("query", "").strip()
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    cache = load_cache()
    q_lower = query.lower()
    words = [w for w in q_lower.split() if w]
    cached_results = [
        {
            "id": f["id"],
            "name": f["name"],
            "mimeType": f.get("mimeType", ""),
            "webViewLink": f.get("webViewLink", ""),
            "modifiedTime": f.get("modifiedTime", ""),
        }
        for f in cache.get("files", [])
        if any(w in f.get("name", "").lower() for w in words)
    ]

    if cached_results:
        return JsonResponse({"query": query, "results": cached_results[:20], "source": "cache"})

    creds = get_creds()
    if not creds:
        return JsonResponse({"query": query, "results": [], "source": "cache"})

    try:
        folder_cfg = load_folder_config()
        service = drive_service(creds)
        escaped = query.replace("'", "\\'")
        conditions = [f"name contains '{escaped}'", "trashed = false", MIME_FILTER]
        if folder_cfg and folder_cfg.get("folder_id"):
            conditions.append(f"'{folder_cfg['folder_id']}' in parents")
        results = (
            service.files()
            .list(
                q=" and ".join(conditions),
                pageSize=20,
                fields="files(id, name, mimeType, modifiedTime, webViewLink, iconLink, size)",
                orderBy="modifiedTime desc",
            )
            .execute()
        )
        return JsonResponse({"query": query, "results": results.get("files", []), "source": "live"})
    except Exception as e:
        logger.warning("Live search failed, returning empty: %s", e)
        return JsonResponse({"query": query, "results": [], "source": "error"})
