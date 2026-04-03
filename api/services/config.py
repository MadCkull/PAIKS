from pathlib import Path
from django.conf import settings
import json

STORAGE_DIR = settings.STORAGE_DIR

TOKEN_PATH = STORAGE_DIR / "token.json"
CREDENTIALS_PATH = STORAGE_DIR / "credentials.json"
SYNC_CACHE_PATH = STORAGE_DIR / "drive_cache.json"
FOLDER_CONFIG_PATH = STORAGE_DIR / "folder_config.json"
CHROMA_PATH = STORAGE_DIR / "chroma_db"
LLM_CONFIG_PATH = STORAGE_DIR / "llm_config.json"
LOCAL_FILES_PATH = STORAGE_DIR / "local_files"
LOCAL_FILES_CACHE = STORAGE_DIR / "local_files_cache.json"

LOCAL_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv"}

LOCAL_FILES_PATH.mkdir(exist_ok=True, parents=True)

_DEFAULT_LLM_CONFIG = {
    "base_url": "http://localhost:11434",
    "model": "llama3.2",
    "provider": "ollama",
}

def load_cache():
    if SYNC_CACHE_PATH.exists():
        return json.loads(SYNC_CACHE_PATH.read_text(encoding="utf-8"))
    return {"files": [], "synced_at": None}

def save_cache(data):
    SYNC_CACHE_PATH.write_text(json.dumps(data, default=str), encoding="utf-8")

def load_folder_config():
    if FOLDER_CONFIG_PATH.exists():
        try:
            return json.loads(FOLDER_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None

def save_folder_config(folder_id, folder_name):
    FOLDER_CONFIG_PATH.write_text(
        json.dumps({"folder_id": folder_id, "folder_name": folder_name}),
        encoding="utf-8",
    )

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
