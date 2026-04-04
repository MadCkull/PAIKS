import time
import queue
from django.http import StreamingHttpResponse
from api.services.event_bus import add_client, remove_client, broadcast_event

def event_stream(request):
    """
    Server-Sent Events endpoint to stream realtime syncing progress and file states.
    """
    def generate():
        client_queue = queue.Queue(maxsize=100)
        add_client(client_queue)
        
        # Send an initial connection event
        yield "data: {\"type\": \"connected\", \"data\": {}}\n\n"
        
        try:
            while True:
                # Block until an event is ready, or timeout to send a keepalive ping
                try:
                    message = client_queue.get(timeout=15)
                    yield message
                except queue.Empty:
                    # Keepalive ping
                    yield ": ping\n\n"
        except Exception:
            pass
        finally:
            remove_client(client_queue)

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no' # Disable Nginx buffering if applicable
    return response

def debug_broadcast(request):
    """Test endpoint just to ping the stream"""
    broadcast_event("test", {"msg": "Hello from backend!"})
    from django.http import JsonResponse
    return JsonResponse({"status": "ok"})
