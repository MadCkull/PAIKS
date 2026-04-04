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
            # Update only specific allowed keys
            for key in ["cloud_enabled", "local_enabled", "local_root_path", "drive_folder_id", "drive_folder_name"]:
                if key in data:
                    current[key] = data[key]
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
