import queue
import json
import logging
import threading

logger = logging.getLogger(__name__)

# List of queues for connected SSE clients
_clients = []
_lock = threading.Lock()

def add_client(q: queue.Queue):
    with _lock:
        _clients.append(q)

def remove_client(q: queue.Queue):
    with _lock:
        if q in _clients:
            _clients.remove(q)

def broadcast_event(event_type: str, data: dict):
    payload = json.dumps({"type": event_type, "data": data})
    with _lock:
        for q in _clients:
            try:
                # Provide a message in standard SSE format
                q.put(f"data: {payload}\n\n", block=False)
            except queue.Full:
                pass
            except Exception as e:
                logger.error(f"Error putting to SSE queue: {e}")
