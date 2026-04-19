"""
Status Broadcaster — The single system responsible for pushing real-time status to the UI.

Instead of the frontend polling /drive/stats, /rag/status, and /rag/llm/status every 2 seconds,
this background thread periodically collects snapshots and broadcasts them via SSE ONLY when
data has actually changed. Any backend action (index, delete, selection change) can also trigger
an immediate broadcast by calling trigger_immediate_broadcast().

This eliminates the polling storm (C-4), cascading duplicate refreshes (C-5),
and LLM over-polling (M-6) identified in the audit.
"""

import json
import time
import logging
import threading
from typing import Optional

from api.services.event_bus import broadcast_event

logger = logging.getLogger(__name__)

# ── State ───────────────────────────────────────────────────────
_running = False
_thread: Optional[threading.Thread] = None
_immediate_event = threading.Event()  # Signal for immediate broadcast

# Last broadcast snapshots (used for change detection)
_last_drive_hash = ""
_last_rag_hash = ""
_last_llm_hash = ""


def _collect_drive_stats() -> dict:
    """Collect the same data as GET /api/drive/stats, but internally."""
    try:
        from api.models import DocumentTrack
        from api.services.google_auth import get_creds
        from api.services.config import load_app_settings, load_folder_config
        from django.db import close_old_connections

        close_old_connections()

        creds = get_creds()
        app_settings = load_app_settings()

        cloud_total = DocumentTrack.objects.filter(source="cloud").count()
        local_total = DocumentTrack.objects.filter(source="local").count()
        indexed_total = DocumentTrack.objects.filter(sync_status="synced").count()
        syncing_total = DocumentTrack.objects.filter(sync_status="syncing").count()
        pending_total = DocumentTrack.objects.filter(sync_status="pending").count()
        disabled_total = DocumentTrack.objects.filter(sync_status="disabled").count()
        error_total = DocumentTrack.objects.filter(sync_status="error").count()

        return {
            "authenticated": creds is not None,
            "cloud_enabled": app_settings.get("cloud_enabled", True),
            "local_enabled": app_settings.get("local_enabled", False),
            "cloud_total": cloud_total,
            "local_total": local_total,
            "documents_total": cloud_total + local_total,
            "indexed_total": indexed_total,
            "syncing_total": syncing_total,
            "pending_total": pending_total,
            "disabled_total": disabled_total,
            "error_total": error_total,
            "folder": load_folder_config(),
            "local_root": app_settings.get("local_root_path"),
        }
    except Exception as e:
        logger.debug(f"Drive stats collection failed: {e}")
        return {}


def _collect_rag_status() -> dict:
    """Collect the same data as GET /api/rag/status, but internally."""
    try:
        from api.services.rag.indexer import get_qdrant_client, LOCAL_COLLECTION, CLOUD_COLLECTION

        client = get_qdrant_client()
        local_count = client.get_collection(LOCAL_COLLECTION).points_count if client.collection_exists(LOCAL_COLLECTION) else 0
        cloud_count = client.get_collection(CLOUD_COLLECTION).points_count if client.collection_exists(CLOUD_COLLECTION) else 0
        total_chunks = local_count + cloud_count

        return {
            "indexed": total_chunks > 0,
            "total_chunks": total_chunks,
        }
    except Exception as e:
        logger.debug(f"RAG status collection failed: {e}")
        return {"indexed": False, "total_chunks": 0}


def _collect_llm_status() -> dict:
    """Collect the same data as GET /api/rag/llm/status, but internally."""
    try:
        from api.services.llm_client import ollama_list_models
        from api.services.config import load_llm_config

        cfg = load_llm_config()
        models = ollama_list_models(cfg.get("base_url", "http://localhost:11434"))
        return {
            "reachable": True,
            "provider": cfg.get("provider", "ollama"),
            "current_model": cfg.get("model", ""),
            "base_url": cfg.get("base_url", ""),
            "available_models": models,
        }
    except Exception:
        return {"reachable": False}


def _hash_snapshot(data: dict) -> str:
    """Fast, deterministic hash of a dict for change detection."""
    return json.dumps(data, sort_keys=True, default=str)


def _broadcast_cycle():
    """Run one full broadcast cycle — collect, compare, broadcast if changed."""
    global _last_drive_hash, _last_rag_hash, _last_llm_hash

    # ── Drive stats (always check) ─────────────────────────────
    drive_data = _collect_drive_stats()
    drive_hash = _hash_snapshot(drive_data)
    if drive_hash != _last_drive_hash:
        _last_drive_hash = drive_hash
        broadcast_event("drive_stats", drive_data)

    # ── RAG status (always check) ──────────────────────────────
    rag_data = _collect_rag_status()
    rag_hash = _hash_snapshot(rag_data)
    if rag_hash != _last_rag_hash:
        _last_rag_hash = rag_hash
        broadcast_event("rag_status", rag_data)

    # ── LLM status (check less frequently — handled by caller) ─
    llm_data = _collect_llm_status()
    llm_hash = _hash_snapshot(llm_data)
    if llm_hash != _last_llm_hash:
        _last_llm_hash = llm_hash
        broadcast_event("llm_status", llm_data)


def _broadcaster_loop():
    """Background loop that periodically broadcasts status snapshots."""
    global _running

    # Wait a few seconds for Django to fully initialize
    time.sleep(3)
    logger.info("Status broadcaster started.")

    llm_check_counter = 0
    LLM_CHECK_INTERVAL = 3  # Check LLM every 3rd cycle (i.e., every 30s if cycle = 10s)

    while _running:
        try:
            global _last_llm_hash

            # Drive + RAG stats (every cycle)
            drive_data = _collect_drive_stats()
            drive_hash = _hash_snapshot(drive_data)
            if drive_hash != _last_drive_hash:
                globals()["_last_drive_hash"] = drive_hash
                broadcast_event("drive_stats", drive_data)

            rag_data = _collect_rag_status()
            rag_hash = _hash_snapshot(rag_data)
            if rag_hash != _last_rag_hash:
                globals()["_last_rag_hash"] = rag_hash
                broadcast_event("rag_status", rag_data)

            # LLM status (every Nth cycle to avoid hammering Ollama)
            llm_check_counter += 1
            if llm_check_counter >= LLM_CHECK_INTERVAL:
                llm_check_counter = 0
                llm_data = _collect_llm_status()
                llm_hash = _hash_snapshot(llm_data)
                if llm_hash != _last_llm_hash:
                    globals()["_last_llm_hash"] = llm_hash
                    broadcast_event("llm_status", llm_data)

        except Exception as e:
            logger.debug(f"Broadcaster cycle error: {e}")

        # Wait 10 seconds OR until an immediate broadcast is requested
        triggered = _immediate_event.wait(timeout=10)
        if triggered:
            _immediate_event.clear()


def trigger_immediate_broadcast():
    """Signal the broadcaster to run a cycle immediately.
    Called by sync_manager and drive views after state-changing actions.
    """
    _immediate_event.set()


def start_status_broadcaster():
    """Start the background broadcaster thread."""
    global _running, _thread

    if _running:
        return

    _running = True
    _thread = threading.Thread(target=_broadcaster_loop, daemon=True)
    _thread.start()


def stop_status_broadcaster():
    """Stop the broadcaster thread."""
    global _running
    _running = False
    _immediate_event.set()  # Wake the thread so it exits
    if _thread:
        _thread.join(timeout=2)
