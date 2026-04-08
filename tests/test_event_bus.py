"""
Tests for api.services.event_bus — SSE broadcasting infrastructure.
"""
import pytest
import queue
import json
from api.services.event_bus import add_client, remove_client, broadcast_event, _clients, _lock


class TestEventBus:
    """Validates the SSE pub/sub system that powers real-time UI updates."""

    def setup_method(self):
        """Clean the global client list before each test."""
        with _lock:
            _clients.clear()

    def teardown_method(self):
        with _lock:
            _clients.clear()

    def test_add_client_registers_queue(self):
        q = queue.Queue()
        add_client(q)
        with _lock:
            assert q in _clients

    def test_remove_client_unregisters_queue(self):
        q = queue.Queue()
        add_client(q)
        remove_client(q)
        with _lock:
            assert q not in _clients

    def test_remove_nonexistent_client_is_safe(self):
        q = queue.Queue()
        remove_client(q)  # Should not raise

    def test_broadcast_delivers_to_all_clients(self):
        q1 = queue.Queue()
        q2 = queue.Queue()
        add_client(q1)
        add_client(q2)

        broadcast_event("sync_update", {"file_id": "abc", "status": "synced"})

        msg1 = q1.get_nowait()
        msg2 = q2.get_nowait()

        parsed1 = json.loads(msg1.replace("data: ", "").strip())
        parsed2 = json.loads(msg2.replace("data: ", "").strip())

        assert parsed1["type"] == "sync_update"
        assert parsed1["data"]["status"] == "synced"
        assert parsed2["type"] == "sync_update"

    def test_broadcast_sse_format(self):
        """SSE spec requires 'data: {json}\n\n' format."""
        q = queue.Queue()
        add_client(q)

        broadcast_event("system_health", {"state": "synced"})

        raw = q.get_nowait()
        assert raw.startswith("data: ")
        assert raw.endswith("\n\n")
        payload = json.loads(raw[6:].strip())
        assert payload["type"] == "system_health"
        assert payload["data"]["state"] == "synced"

    def test_broadcast_skips_full_queue(self):
        """If a client queue is full, it should be silently skipped."""
        q = queue.Queue(maxsize=1)
        add_client(q)

        # Fill the queue
        broadcast_event("test", {"a": 1})
        # This should NOT raise
        broadcast_event("test", {"b": 2})

        # Only the first message should be in the queue
        assert q.qsize() == 1

    def test_broadcast_system_log_payload(self):
        """system_log events carry {time, level, msg} dicts."""
        q = queue.Queue()
        add_client(q)

        log_data = {"time": "12:00:00", "level": "success", "msg": "test.txt indexed successfully."}
        broadcast_event("system_log", log_data)

        raw = q.get_nowait()
        payload = json.loads(raw[6:].strip())
        assert payload["type"] == "system_log"
        assert payload["data"]["level"] == "success"
        assert payload["data"]["msg"] == "test.txt indexed successfully."
