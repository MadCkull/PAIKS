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

LOCAL_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".xls", ".pptx"}

LOCAL_FILES_PATH.mkdir(exist_ok=True, parents=True)

_DEFAULT_APP_SETTINGS = {
    "general": {
        "system_prompt": "",
        "context_memory_limit": 6,
        "accent_color": "purple",
    },
    "sources": {
        "cloud_enabled": False,
        "local_enabled": True,
        "local_root_path": None,
        "drive_folder_id": None,
        "drive_folder_name": None,
    },
    "rag": {
        "chunk_size": 512,
        "chunk_overlap": 64,
        "top_k": 30,
        "top_n": 5,
        "rerank_enabled": True,
        "auto_summarise": False,
    },
    "models": {
        "cloud_llm_enabled": False,
        "cloud_provider": "Google Gemini",
        "cloud_key": "",
        "cloud_model": "",
        "active_llm": "local",
        "embed_model": "nomic-embed-text",
    },
    "data": {
        "sync_interval": "30",
    }
}

_DEFAULT_LLM_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "llama3.2",
    "provider": "ollama",
}

def load_app_settings() -> dict:
    if APP_SETTINGS_PATH.exists():
        try:
            data = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
            # Category-based merge for robustness
            settings = json.loads(json.dumps(_DEFAULT_APP_SETTINGS)) # deep copy
            for cat in settings:
                if cat in data and isinstance(data[cat], dict):
                    settings[cat].update(data[cat])
            return settings
        except Exception:
            pass
    return json.loads(json.dumps(_DEFAULT_APP_SETTINGS))

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
    src = settings.get("sources", {})
    if src.get("drive_folder_id"):
        return {"folder_id": src["drive_folder_id"], "folder_name": src["drive_folder_name"]}
    return None

def save_folder_config(folder_id, folder_name):
    settings = load_app_settings()
    if "sources" not in settings: settings["sources"] = {}
    settings["sources"]["drive_folder_id"] = folder_id
    settings["sources"]["drive_folder_name"] = folder_name
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

# ── Cloud model list (single source of truth) ──────────────────────────────
# ALL backend code must use this function. The GEMINI_MODELS env var is the
# only place where available cloud model names are defined.

def get_cloud_models(provider: str = "Google Gemini") -> list[str]:
    """Return the list of available cloud models from .env.
    
    GEMINI_MODELS is the canonical source — comma-separated model names.
    Returns a non-empty list; falls back to the first model saved in system.json
    if the env var is somehow missing, or an empty list if nothing is available.
    """
    import os
    if provider == "Google Gemini":
        raw = os.environ.get("GEMINI_MODELS", "").strip()
        if raw:
            return [m.strip() for m in raw.split(",") if m.strip()]
    # Future providers: elif provider == "OpenAI": ...
    return []

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
