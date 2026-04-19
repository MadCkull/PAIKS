import os
import time
import queue
import logging
import hashlib
import threading
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from django.utils import timezone
from api.models import DocumentTrack
from api.services.config import load_app_settings, LOCAL_ALLOWED_EXTENSIONS
from api.services.event_bus import broadcast_event
from api.services.status_broadcaster import trigger_immediate_broadcast

logger = logging.getLogger(__name__)

# Configure a file handler specifically for sync manager
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
file_handler = logging.FileHandler("logs/sync.log")
file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(file_handler)
logger.setLevel(logging.INFO)


class SSELogHandler(logging.Handler):
    """Pushes every log record to connected SSE clients in real-time."""
    def emit(self, record):
        try:
            from datetime import datetime
            msg = record.getMessage()
            level = "info"
            if record.levelno >= logging.ERROR:
                level = "error"
            elif record.levelno >= logging.WARNING:
                level = "warning"
            elif any(kw in msg.lower() for kw in ("successfully", "indexed", "deleted", "synced")):
                level = "success"

            payload = {
                "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": level,
                "msg": msg
            }
            broadcast_event("system_log", payload)
        except Exception:
            pass


sse_handler = SSELogHandler()
logger.addHandler(sse_handler)

# ── Threading State ──────────────────────────────────────────────
_running = False
_worker_thread = None
_observer = None
_polling_thread = None

# Debounce timers for watchdog (prevents duplicate rapid-fire events)
_debounce_timers = {}
_debounce_lock = threading.Lock()
DEBOUNCE_SECONDS = 1.5


def get_file_hash(filepath: str) -> Optional[str]:
    """Calculate SHA-256 of a file to detect content changes."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return None


def _compute_and_broadcast_health():
    """Query the DB for the TRUE overall system health and broadcast it.
    This is the SINGLE SOURCE OF TRUTH for the badge state."""
    try:
        selected_docs = DocumentTrack.objects.filter(is_selected=True)
        syncing_count = selected_docs.filter(sync_status__in=["syncing", "pending"]).count()
        error_count = selected_docs.filter(sync_status="error").count()
        total_selected = selected_docs.count()
        synced_count = selected_docs.filter(sync_status="synced").count()

        if syncing_count > 0:
            state = "syncing"
        elif error_count > 0:
            state = "warning"  # some files have issues
        elif total_selected > 0 and synced_count == total_selected:
            state = "synced"   # ALL selected files are perfectly indexed
        elif total_selected == 0:
            state = "synced"   # nothing selected, nothing to worry about
        else:
            state = "warning"  # some selected files aren't synced

        broadcast_event("system_health", {"state": state})
        trigger_immediate_broadcast()
    except Exception:
        pass


class LocalFileHandler(FileSystemEventHandler):
    """Watches for local file changes from the OS."""

    def on_created(self, event):
        if not event.is_directory:
            self._debounced_change(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._debounced_change(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._handle_deleted(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_deleted(event.src_path)
            self._debounced_change(event.dest_path)

    def _debounced_change(self, filepath: str):
        """Debounce rapid-fire events for the same file.
        Only the LAST change within DEBOUNCE_SECONDS actually gets queued."""
        ext = Path(filepath).suffix.lower()
        if ext not in LOCAL_ALLOWED_EXTENSIONS:
            return

        with _debounce_lock:
            # Cancel any existing timer for this file
            if filepath in _debounce_timers:
                _debounce_timers[filepath].cancel()

            timer = threading.Timer(DEBOUNCE_SECONDS, self._handle_change, args=[filepath])
            _debounce_timers[filepath] = timer
            timer.start()

    def _handle_change(self, filepath: str):
        """Actually process the file change after debounce."""
        with _debounce_lock:
            _debounce_timers.pop(filepath, None)

        file_hash = get_file_hash(filepath)
        if not file_hash:
            return

        file_id = f"local__{filepath}"

        from django.db import transaction
        try:
            with transaction.atomic():
                doc, created = DocumentTrack.objects.get_or_create(
                    file_id=file_id,
                    defaults={
                        "name": os.path.basename(filepath),
                        "source": "local",
                        "content_hash": file_hash,
                        "sync_status": "pending",
                        "last_modified": timezone.now()
                    }
                )

                if not created:
                    if doc.content_hash != file_hash:
                        doc.content_hash = file_hash
                        doc.last_modified = timezone.now()
                        # Only set pending if the file is actually selected
                        if doc.is_selected:
                            doc.sync_status = "pending"
                        doc.save()

                if doc.is_selected and doc.sync_status == "pending":
                    from api.models import SyncJob
                    SyncJob.objects.create(document=doc, action="index")
                    logger.info(f"Change detected in {os.path.basename(filepath)}, queued for indexing.")
                    _compute_and_broadcast_health()

        except Exception as e:
            logger.error(f"Error handling file change for {os.path.basename(filepath)}: {e}")

    def _handle_deleted(self, filepath: str):
        file_id = f"local__{filepath}"
        try:
            from api.models import SyncJob
            from django.db import transaction
            
            with transaction.atomic():
                doc = DocumentTrack.objects.filter(file_id=file_id).first()
                if doc:
                    doc.sync_status = "disabled"
                    doc.save()
                    SyncJob.objects.create(document=doc, action="delete")
                    logger.info(f"{os.path.basename(filepath)} was deleted from disk/unselected.")
        except Exception as e:
            logger.error(f"Error handling deletion of {os.path.basename(filepath)}: {e}")


def _index_worker():
    """Background thread that processes indexing/deletion jobs from the Database Outbox."""
    from api.services.rag.ingestion.parsers import parse_local_file, parse_cloud_file
    from api.services.rag.ingestion.chunking import chunk_documents
    from api.services.rag.ingestion.pipeline import ingest_nodes_to_collection
    from api.services.rag.indexer import LOCAL_COLLECTION, CLOUD_COLLECTION
    from api.services.google_auth import get_creds
    from api.services.google_drive import drive_service
    from api.services.rag.indexer import get_qdrant_client
    from qdrant_client.http import models as qmodels

    global _running
    while _running:
        try:
            from django.db import close_old_connections, transaction
            close_old_connections()
            from api.models import SyncJob, DocumentTrack
            
            # Fetch the oldest pending job
            with transaction.atomic():
                job = SyncJob.objects.select_for_update(skip_locked=True).filter(status='pending').order_by('created_at').first()
                if not job:
                    time.sleep(2)
                    continue
                # Mark as processing
                job.status = 'processing'
                job.save()

            action = job.action
            doc = job.document

            # ── DELETE ──────────────────────────────────────────
            if action == "delete":
                fid = doc.file_id.replace("cloud__", "", 1) if doc.source == "cloud" else doc.file_id
                display_name = doc.name
                
                try:
                    client = get_qdrant_client()
                    col = CLOUD_COLLECTION if doc.source == "cloud" else LOCAL_COLLECTION
                    if client.collection_exists(col):
                        client.delete(
                            collection_name=col,
                            points_selector=qmodels.FilterSelector(
                                filter=qmodels.Filter(
                                    must=[
                                        qmodels.FieldCondition(
                                            key="file_id",
                                            match=qmodels.MatchValue(value=fid)
                                        )
                                    ]
                                )
                            )
                        )
                    logger.info(f"{display_name} removed from knowledge base.")
                    job.status = 'completed'
                except Exception as e:
                    logger.error(f"Failed to remove {display_name}: {e}")
                    job.status = 'failed'
                    job.error_message = str(e)
                
                job.save()
                _compute_and_broadcast_health()

            # ── INDEX ───────────────────────────────────────────
            elif action == "index":
                # Skip if user deselected it before we got around to indexing
                if not doc.is_selected:
                    job.status = 'completed'
                    job.save()
                    continue

                # Skip directories silently
                if doc.source == "local":
                    filepath = doc.file_id.replace("local__", "", 1)
                    if os.path.exists(filepath) and os.path.isdir(filepath):
                        doc.delete()
                        job.status = 'completed'
                        job.save()
                        continue

                logger.info(f"Processing {doc.name}...")
                doc.sync_status = "syncing"
                doc.save()
                broadcast_event("sync_update", {"file_id": doc.file_id, "name": doc.name, "status": "syncing"})
                _compute_and_broadcast_health()

                try:
                    parsed_docs = []
                    col = None

                    if doc.source == "local":
                        filepath = doc.file_id.replace("local__", "", 1)
                        if not os.path.exists(filepath):
                            raise Exception("File deleted before index started")

                        # Clean old vectors
                        client = get_qdrant_client()
                        if client.collection_exists(LOCAL_COLLECTION):
                            client.delete(
                                collection_name=LOCAL_COLLECTION,
                                points_selector=qmodels.FilterSelector(
                                    filter=qmodels.Filter(
                                        must=[
                                            qmodels.FieldCondition(
                                                key="file_id",
                                                match=qmodels.MatchValue(value=doc.file_id)
                                            )
                                        ]
                                    )
                                )
                            )

                        file_dict = {
                            "id": doc.file_id,
                            "name": doc.name,
                            "local_path": filepath,
                            "modified": str(doc.last_modified)
                        }
                        parsed = parse_local_file(file_dict)
                        if parsed:
                            parsed_docs.append(parsed)
                        col = LOCAL_COLLECTION

                    elif doc.source == "cloud":
                        creds = get_creds()
                        if not creds:
                            raise Exception("Not authenticated with Google Drive")
                        service = drive_service(creds)

                        fid = doc.file_id.replace("cloud__", "", 1)
                        
                        client = get_qdrant_client()
                        if client.collection_exists(CLOUD_COLLECTION):
                            client.delete(
                                collection_name=CLOUD_COLLECTION,
                                points_selector=qmodels.FilterSelector(
                                    filter=qmodels.Filter(
                                        must=[
                                            qmodels.FieldCondition(
                                                key="file_id",
                                                match=qmodels.MatchValue(value=fid)
                                            )
                                        ]
                                    )
                                )
                            )


                        try:
                            # Must fetch mimeType and webViewLink dynamically for proper parsing
                            meta = service.files().get(fileId=fid, fields="mimeType, webViewLink").execute()
                        except Exception as meta_e:
                            logger.error(f"Failed to fetch metadata for {doc.name}: {meta_e}")
                            meta = {}
                            
                        file_dict = {
                            "id": fid,
                            "name": doc.name,
                            "mime": meta.get("mimeType", ""),
                            "link": meta.get("webViewLink", ""),
                            "modified": doc.last_modified.isoformat() if doc.last_modified else ""
                        }
                        parsed = parse_cloud_file(service, file_dict)
                        if parsed:
                            parsed_docs.append(parsed)
                        col = CLOUD_COLLECTION

                    if parsed_docs:
                        nodes = chunk_documents(parsed_docs)
                        ingest_nodes_to_collection(nodes, col)
                        
                        doc.sync_status = "synced"
                        doc.error_message = ""
                        doc.save()
                        
                        job.status = 'completed'
                        logger.info(f"{doc.name} indexed successfully.")
                        broadcast_event("sync_update", {"file_id": doc.file_id, "name": doc.name, "status": "synced"})
                    else:
                        doc.sync_status = "error"
                        doc.error_message = "Could not extract text (unsupported format or empty)"
                        doc.save()
                        
                        job.status = 'failed'
                        job.error_message = doc.error_message
                        logger.warning(f"{doc.name} could not be read (unsupported or empty).")
                        broadcast_event("sync_update", {"file_id": doc.file_id, "name": doc.name, "status": "error"})
                        
                    job.save()

                except Exception as e:
                    doc.sync_status = "error"
                    doc.error_message = str(e)
                    doc.save()
                    
                    job.status = 'failed'
                    job.error_message = str(e)
                    job.save()
                    
                    broadcast_event("sync_update", {"file_id": doc.file_id, "name": doc.name, "status": "error"})
                    logger.error(f"Failed to index {doc.name}: {e}")

                _compute_and_broadcast_health()

        except Exception as e:
            logger.error(f"Worker error: {e}")
            time.sleep(2)


def _cloud_poll_worker():
    """Background thread that polls Google Drive for changes every 60s."""
    from api.services.google_auth import get_creds
    from api.services.google_drive import drive_service, MIME_FILTER
    from dateutil.parser import parse as parse_date

    global _running
    while _running:
        try:
            from django.db import close_old_connections
            close_old_connections()
            
            settings = load_app_settings()
            if settings.get("cloud_enabled"):
                creds = get_creds()
                if creds:
                    service = drive_service(creds)
                    folder_id = settings.get("drive_folder_id")
                    base_q = f"trashed = false and {MIME_FILTER}"
                    if folder_id:
                        base_q = f"'{folder_id}' in parents and trashed = false and {MIME_FILTER}"

                    page_token = None
                    all_cloud_ids = set()

                    from django.db import transaction
                    from api.models import SyncJob
                    
                    while True:
                        results = service.files().list(
                            q=base_q,
                            fields="nextPageToken, files(id, name, modifiedTime, mimeType)",
                            pageSize=100,
                            pageToken=page_token
                        ).execute()

                        files = results.get("files", [])
                        for f in files:
                            fid = f"cloud__{f['id']}"
                            all_cloud_ids.add(fid)
                            mod_time = parse_date(f['modifiedTime'])

                            with transaction.atomic():
                                doc, created = DocumentTrack.objects.get_or_create(
                                    file_id=fid,
                                    defaults={
                                        "name": f['name'],
                                        "source": "cloud",
                                        "last_modified": mod_time,
                                        "sync_status": "pending"
                                    }
                                )

                                needs_index = False
                                if not created and (doc.last_modified is None or doc.last_modified < mod_time):
                                    doc.last_modified = mod_time
                                    # Set to pending only if user still wants it selected
                                    if doc.is_selected:
                                        doc.sync_status = "pending"
                                        needs_index = True
                                    doc.save()

                                if created and doc.is_selected:
                                    needs_index = True

                                if needs_index:
                                    SyncJob.objects.create(document=doc, action="index")

                        page_token = results.get("nextPageToken")
                        if not page_token:
                            break

                    # Mark missing files as disabled and queue delete for them
                    with transaction.atomic():
                        missing = DocumentTrack.objects.filter(source="cloud", is_selected=True).exclude(file_id__in=all_cloud_ids)
                        for doc in missing:
                            doc.sync_status = "disabled"
                            doc.save()
                            SyncJob.objects.create(document=doc, action="delete")

        except Exception as e:
            logger.error(f"Cloud sync error: {e}")

        # Poll every 60 seconds
        for _ in range(60):
            if not _running:
                break
            time.sleep(1)


def start_sync_engine():
    """Starts the watchdog observer and background worker threads."""
    global _observer, _worker_thread, _polling_thread, _running

    if _running:
        return

    _running = True

    _worker_thread = threading.Thread(target=_index_worker, daemon=True)
    _worker_thread.start()

    _polling_thread = threading.Thread(target=_cloud_poll_worker, daemon=True)
    _polling_thread.start()

    # Start Watchdog
    settings = load_app_settings()
    local_root = settings.get("local_root_path")
    if settings.get("local_enabled") and local_root and os.path.exists(local_root):
        _observer = Observer()
        event_handler = LocalFileHandler()
        _observer.schedule(event_handler, local_root, recursive=True)
        try:
            _observer.start()
            logger.info(f"File watcher started for {local_root}")
        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")


def stop_sync_engine():
    """Stops all background processes cleanly."""
    global _observer, _worker_thread, _polling_thread, _running
    _running = False

    if _observer:
        _observer.stop()
        _observer.join()
        _observer = None

    if _worker_thread:
        _worker_thread.join(timeout=2)
    if _polling_thread:
        _polling_thread.join(timeout=2)
