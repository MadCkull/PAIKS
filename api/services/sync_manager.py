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

logger = logging.getLogger(__name__)

# A thread-safe queue to hold indexing jobs
_index_queue = queue.Queue()
_observer = None
_worker_thread = None
_polling_thread = None
_running = False

def get_file_hash(filepath: str) -> Optional[str]:
    """Calculate SHA-256 of a file to detect content changes."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.warning(f"Could not hash {filepath}: {e}")
        return None

class LocalFileHandler(FileSystemEventHandler):
    """Watches for local file changes from the OS."""
    
    def on_created(self, event):
        if not event.is_directory:
            self._handle_change(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory:
            self._handle_change(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory:
            self._handle_deleted(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle_deleted(event.src_path)
            self._handle_change(event.dest_path, "created")

    def _handle_change(self, filepath: str, action: str):
        ext = Path(filepath).suffix.lower()
        if ext not in LOCAL_ALLOWED_EXTENSIONS:
            return

        file_hash = get_file_hash(filepath)
        if not file_hash:
            return

        file_id = f"local__{filepath}"
        
        # We need to wrap DB operations to ensure they are thread safe
        # In Django, models are thread-safe as long as each thread has its own connection.
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
                    # Only queue for sync if the content actually changed and it is selected
                    if doc.content_hash != file_hash:
                        doc.content_hash = file_hash
                        doc.sync_status = "pending"
                        doc.last_modified = timezone.now()
                        doc.save()

                if doc.is_selected and doc.sync_status == "pending":
                    _index_queue.put({"action": "index", "doc_id": doc.id})
                    
        except Exception as e:
            logger.error(f"Error handling file change for {filepath}: {e}")

    def _handle_deleted(self, filepath: str):
        file_id = f"local__{filepath}"
        try:
            doc = DocumentTrack.objects.filter(file_id=file_id).first()
            if doc:
                doc.sync_status = "disabled"
                doc.save()
                _index_queue.put({"action": "delete", "file_id": file_id})
        except Exception as e:
            logger.error(f"Error handling deletion of {filepath}: {e}")


def _index_worker():
    """Background thread that actually processes chunks into Qdrant."""
    from api.services.rag.ingestion.parsers import parse_local_file, parse_cloud_file
    from api.services.rag.ingestion.chunking import chunk_documents
    from api.services.rag.ingestion.pipeline import ingest_nodes_to_collection
    from api.services.rag.indexer import LOCAL_COLLECTION, CLOUD_COLLECTION
    from api.services.google_auth import get_creds
    from api.services.google_drive import drive_service
    from qdrant_client import QdrantClient
    from api.services.rag.indexer import get_qdrant_client
    
    global _running
    while _running:
        try:
            job = _index_queue.get(timeout=2)
            
            action = job.get("action")
            if action == "delete":
                fid = job.get("file_id")
                try:
                    client = get_qdrant_client()
                    col = CLOUD_COLLECTION if fid.startswith("cloud__") else LOCAL_COLLECTION
                    if client.collection_exists(col):
                        client.delete(
                            collection_name=col,
                            points_selector={"filter": {"must": [{"key": "file_id", "match": {"value": fid}}]}}
                        )
                except Exception as e:
                    logger.error(f"Deletion from Qdrant failed for {fid}: {e}")
            
            elif action == "index":
                doc_id = job.get("doc_id")
                doc = DocumentTrack.objects.get(id=doc_id)
                doc.sync_status = "syncing"
                doc.save()
                broadcast_event("sync_update", {"file_id": doc.file_id, "name": doc.name, "status": "syncing"})

                # Simulate progress via state (SSE will watch this)
                try:
                    parsed_docs = []
                    col = None
                    if doc.source == "local":
                        filepath = doc.file_id.replace("local__", "", 1)
                        # We delete old points before adding new ones for this file
                        client = get_qdrant_client()
                        if client.collection_exists(LOCAL_COLLECTION):
                            client.delete(
                                collection_name=LOCAL_COLLECTION,
                                points_selector={"filter": {"must": [{"key": "file_id", "match": {"value": doc.file_id}}]}}
                            )
                            
                        # Mock the dictionary format `parse_local_file` expects
                        file_dict = {
                            "id": doc.file_id,
                            "name": doc.name,
                            "local_path": filepath,
                            "modified": str(doc.last_modified)
                        }
                        parsed = parse_local_file(file_dict)
                        if parsed: parsed_docs.append(parsed)
                        col = LOCAL_COLLECTION
                        
                    elif doc.source == "cloud":
                        creds = get_creds()
                        if not creds:
                            raise Exception("Not authenticated with Google Drive")
                        service = drive_service(creds)
                        
                        client = get_qdrant_client()
                        if client.collection_exists(CLOUD_COLLECTION):
                            client.delete(
                                collection_name=CLOUD_COLLECTION,
                                points_selector={"filter": {"must": [{"key": "file_id", "match": {"value": doc.file_id}}]}}
                            )
                            
                        # Need to fetch file metadata or construct it
                        file_dict = {
                            "id": doc.file_id.replace("cloud__", "", 1),
                            "name": doc.name,
                            "modified": str(doc.last_modified)
                        }
                        parsed = parse_cloud_file(service, file_dict)
                        if parsed: parsed_docs.append(parsed)
                        col = CLOUD_COLLECTION
                        
                    if parsed_docs:
                        nodes = chunk_documents(parsed_docs)
                        ingest_nodes_to_collection(nodes, col)
                        
                    doc.sync_status = "synced"
                    doc.error_message = ""
                    doc.save()
                    broadcast_event("sync_update", {"file_id": doc.file_id, "name": doc.name, "status": "synced"})
                except Exception as e:
                    doc.sync_status = "error"
                    doc.error_message = str(e)
                    doc.save()
                    broadcast_event("sync_update", {"file_id": doc.file_id, "name": doc.name, "status": "error", "message": str(e)})
                    logger.error(f"Indexing error for {doc.name}: {e}")
                    
            _index_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Worker thread error: {e}")
            time.sleep(1)

def _cloud_poll_worker():
    """Background thread that polls Google Drive for changes every 60s."""
    from api.services.google_auth import get_creds
    from api.services.google_drive import drive_service, MIME_FILTER
    from dateutil.parser import parse as parse_date
    
    global _running
    while _running:
        try:
            settings = load_app_settings()
            if settings.get("cloud_enabled"):
                creds = get_creds()
                if creds:
                    service = drive_service(creds)
                    # Poll for all files and update DB (MVP simple polling)
                    folder_id = settings.get("drive_folder_id")
                    base_q = f"trashed = false and {MIME_FILTER}"
                    if folder_id:
                        base_q = f"'{folder_id}' in parents and trashed = false and {MIME_FILTER}"
                    
                    page_token = None
                    all_cloud_ids = set()
                    
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
                            
                            doc, created = DocumentTrack.objects.get_or_create(
                                file_id=fid,
                                defaults={
                                    "name": f['name'],
                                    "source": "cloud",
                                    "last_modified": mod_time,
                                    "sync_status": "pending"
                                }
                            )
                            
                            if not created and doc.last_modified < mod_time:
                                doc.last_modified = mod_time
                                doc.sync_status = "pending"
                                doc.save()
                                
                            if doc.is_selected and doc.sync_status == "pending":
                                _index_queue.put({"action": "index", "doc_id": doc.id})
                                
                        page_token = results.get("nextPageToken")
                        if not page_token:
                            break
                    
                    # Mark missing files as disabled
                    DocumentTrack.objects.filter(source="cloud").exclude(file_id__in=all_cloud_ids).update(sync_status="disabled")
                    
        except Exception as e:
            logger.error(f"Cloud poll error: {e}")
            
        # Poll every 60 seconds
        for _ in range(60):
            if not _running: break
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
            logger.info(f"Started OS File Watcher for: {local_root}")
        except Exception as e:
            logger.error(f"Failed to start observer: {e}")

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
