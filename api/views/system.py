import os
import json
import string
import pathlib
from django.http import JsonResponse
from api.services.config import load_app_settings, save_app_settings

def settings_view(request):
    if request.method == "GET":
        return JsonResponse(load_app_settings())
    
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            current = load_app_settings()
            
            # Deep merge logic: for each category in default settings,
            # if the payload has that category, update it.
            for cat in ["general", "sources", "rag", "models", "data"]:
                if cat in data and isinstance(data[cat], dict):
                    if cat not in current: current[cat] = {}
                    current[cat].update(data[cat])
            
            save_app_settings(current)
            return JsonResponse({"status": "ok", "settings": current})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)
            
    return JsonResponse({"error": "Method not allowed"}, status=405)

def browse_local(request):
    path_str = request.GET.get("path", "")
    
    # ── "This PC" / Root Drives ────────────────────────────────
    if not path_str or path_str.lower() == "this pc":
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append({
                    "name": f"Local Disk ({letter}:)",
                    "path": drive,
                    "is_dir": True,
                    "type": "drive"
                })
        return JsonResponse({"path": "This PC", "items": drives})

    # ── Normal Directory Listing ──────────────────────────────
    try:
        p = pathlib.Path(path_str)
        if not p.exists() or not p.is_dir():
            return JsonResponse({"error": "Path does not exist or is not a directory"}, status=404)

        items = []
        # Add ".." for navigating up, unless at drive root
        if p.parent and p.parent != p:
            items.append({
                "name": "..",
                "path": str(p.parent),
                "is_dir": True,
                "type": "up"
            })

        for entry in os.scandir(p):
            try:
                items.append({
                    "name": entry.name,
                    "path": str(pathlib.Path(entry.path)),
                    "is_dir": entry.is_dir(),
                    "size": entry.stat().st_size if entry.is_file() else None,
                    "type": "dir" if entry.is_dir() else "file"
                })
            except (PermissionError, OSError):
                continue
                
        # Sort: Dirs first then names
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        
        return JsonResponse({
            "path": str(p),
            "parts": list(p.parts),
            "items": items
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

def logs(request):
    log_file = pathlib.Path("logs/sync.log")
    if request.method == "POST":
        try:
            if log_file.exists():
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write("")
            return JsonResponse({"status": "cleared"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
    if request.method == "GET":
        try:
            lines = []
            if log_file.exists():
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            # Return last 1000 lines max
            return JsonResponse({"logs": [l.strip() for l in lines[-1000:]]})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
            
    return JsonResponse({"error": "Method not allowed"}, status=405)
def clear_app_cache(request):
    """
    EXTREME cleanup: Wipes all file caches, mirror files, and Django internal cache.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    
    try:
        from django.core.cache import cache
        from django.conf import settings
        import shutil
        
        # 1. Clear Django internal cache
        cache.clear()
        
        # 2. Wipe STORAGE_DIR / cache
        storage_cache = settings.STORAGE_DIR / "cache"
        if storage_cache.exists():
            for item in storage_cache.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception:
                    continue
        
        # Ensure mirror directory exists for future syncs
        (storage_cache / "mirrors").mkdir(parents=True, exist_ok=True)
        
        # 3. (Optional) Wipe logs if they are too big
        log_file = settings.BASE_DIR / "logs" / "paiks.log"
        if log_file.exists():
             with open(log_file, "w") as f: f.write("")

        return JsonResponse({"status": "cleared", "message": "All backend caches wiped successfully"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
