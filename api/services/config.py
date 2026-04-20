from pathlib import Path
from django.conf import settings
import json

STORAGE_DIR = settings.STORAGE_DIR

TOKEN_PATH = STORAGE_DIR / "auth" / "google_token.json"
CREDENTIALS_PATH = STORAGE_DIR / "auth" / "google_creds.json"
SYNC_CACHE_PATH = STORAGE_DIR / "cache" / "drive_cache.json"
FOLDER_CONFIG_PATH = STORAGE_DIR / "config" / "folder_config.json"
APP_SETTINGS_PATH = STORAGE_DIR / "config" / "system.json"
CHROMA_PATH = STORAGE_DIR / "databases" / "chroma_db"
LLM_CONFIG_PATH = STORAGE_DIR / "config" / "llm.json"
LOCAL_FILES_PATH = STORAGE_DIR / "cache" / "mirrors"
LOCAL_FILES_CACHE = STORAGE_DIR / "cache" / "local_files_cache.json"
LOCAL_STATS_CACHE = STORAGE_DIR / "cache" / "local_stats_cache.json"

LOCAL_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv"}

LOCAL_FILES_PATH.mkdir(exist_ok=True, parents=True)

_DEFAULT_APP_SETTINGS = {
    "cloud_enabled": True,
    "local_enabled": True,
    "local_root_path": None,
    "drive_folder_id": None,
    "drive_folder_name": None,
}

_DEFAULT_LLM_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "llama3.2",
    "provider": "ollama",
}

def load_app_settings() -> dict:
    # ── Migration ──────────────────────────────────────────
    if not APP_SETTINGS_PATH.exists() and FOLDER_CONFIG_PATH.exists():
        try:
            old = json.loads(FOLDER_CONFIG_PATH.read_text(encoding="utf-8"))
            settings = dict(_DEFAULT_APP_SETTINGS)
            settings["drive_folder_id"] = old.get("folder_id")
            settings["drive_folder_name"] = old.get("folder_name")
            save_app_settings(settings)
            return settings
        except Exception:
            pass
            
    if APP_SETTINGS_PATH.exists():
        try:
            data = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
            return {**_DEFAULT_APP_SETTINGS, **data}
        except Exception:
            pass
    return dict(_DEFAULT_APP_SETTINGS)

def save_app_settings(data: dict):
    APP_SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

def load_cache():
    if SYNC_CACHE_PATH.exists():
        return json.loads(SYNC_CACHE_PATH.read_text(encoding="utf-8"))
    return {"files": [], "synced_at": None}

def save_cache(data):
    SYNC_CACHE_PATH.write_text(json.dumps(data, default=str), encoding="utf-8")

def load_folder_config():
    # Deprecated: use load_app_settings instead
    settings = load_app_settings()
    if settings.get("drive_folder_id"):
        return {"folder_id": settings["drive_folder_id"], "folder_name": settings["drive_folder_name"]}
    return None

def save_folder_config(folder_id, folder_name):
    settings = load_app_settings()
    settings["drive_folder_id"] = folder_id
    settings["drive_folder_name"] = folder_name
    save_app_settings(settings)

def load_llm_config() -> dict:
    if LLM_CONFIG_PATH.exists():
        try:
            return json.loads(LLM_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return dict(_DEFAULT_LLM_CONFIG)

def save_llm_config(cfg: dict):
    LLM_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def local_files_meta():
    try:
        if LOCAL_FILES_CACHE.exists():
            return json.loads(LOCAL_FILES_CACHE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []

def local_files_meta_save(meta_list):
    LOCAL_FILES_CACHE.write_text(json.dumps(meta_list, ensure_ascii=False, indent=2), encoding="utf-8")

def load_local_stats_cache() -> dict:
    """Load cached local file stats (total, size, types). Avoids rglob on every request."""
    try:
        if LOCAL_STATS_CACHE.exists():
            return json.loads(LOCAL_STATS_CACHE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"total": 0, "size": 0, "file_types": {}}

def save_local_stats_cache(stats: dict):
    """Cache local file stats to disk."""
    LOCAL_STATS_CACHE.write_text(json.dumps(stats, indent=2), encoding="utf-8")
