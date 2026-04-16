"""
Tests for api.services.event_bus — SSE broadcasting infrastructure.

Covers:
  - Client registration / deregistration
  - Broadcast delivery to N clients
  - SSE wire format (data: {json}\n\n)
  - Full-queue resilience
  - Payload structure for specific event types
  - Thread-safety under concurrent access
"""
import pytest
import queue
import json
import threading
from api.services.event_bus import add_client, remove_client, broadcast_event, _clients, _lock


class TestClientRegistration:
    """Validates client queue lifecycle management."""

    def test_add_client_registers_queue(self):
        q = queue.Queue()
        add_client(q)
        with _lock:
            assert q in _clients

    def test_add_multiple_clients(self):
        queues = [queue.Queue() for _ in range(5)]
        for q in queues:
            add_client(q)
        with _lock:
            assert len(_clients) == 5

    def test_remove_client_unregisters_queue(self):
        q = queue.Queue()
        add_client(q)
        remove_client(q)
        with _lock:
            assert q not in _clients

    def test_remove_nonexistent_client_is_safe(self):
        q = queue.Queue()
        remove_client(q)  # Must not raise

    def test_remove_only_target_client(self):
        q1, q2 = queue.Queue(), queue.Queue()
        add_client(q1)
        add_client(q2)
        remove_client(q1)
        with _lock:
            assert q1 not in _clients
            assert q2 in _clients


class TestBroadcastDelivery:
    """Validates message fan-out to all connected SSE clients."""

    def test_broadcast_delivers_to_all_clients(self):
        q1, q2 = queue.Queue(), queue.Queue()
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
        """SSE spec requires 'data: {json}\\n\\n' format."""
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

        broadcast_event("test", {"a": 1})
        broadcast_event("test", {"b": 2})  # Must NOT raise

        assert q.qsize() == 1

    def test_broadcast_to_no_clients(self):
        """Broadcasting with zero clients must not error."""
        broadcast_event("test", {"x": 1})  # Must not raise

    def test_broadcast_preserves_payload_structure(self):
        q = queue.Queue()
        add_client(q)

        data = {"time": "12:00:00", "level": "success", "msg": "test.txt indexed."}
        broadcast_event("system_log", data)

        raw = q.get_nowait()
        payload = json.loads(raw[6:].strip())
        assert payload["type"] == "system_log"
        assert payload["data"]["level"] == "success"
        assert payload["data"]["msg"] == "test.txt indexed."

    def test_broadcast_with_nested_dict(self):
        """Complex nested payloads should survive JSON serialization."""
        q = queue.Queue()
        add_client(q)

        data = {"settings": {"cloud_enabled": True, "nested": {"key": [1, 2, 3]}}}
        broadcast_event("config_update", data)

        raw = q.get_nowait()
        payload = json.loads(raw[6:].strip())
        assert payload["data"]["settings"]["nested"]["key"] == [1, 2, 3]


class TestThreadSafety:
    """Validates that event bus operations are safe under concurrency."""

    def test_concurrent_add_remove(self):
        """Rapid concurrent add/remove should not corrupt the client list."""
        errors = []

        def worker():
            try:
                q = queue.Queue()
                add_client(q)
                broadcast_event("ping", {"n": 1})
                remove_client(q)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == []
        with _lock:
            assert len(_clients) == 0
