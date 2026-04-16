"""
Tests for api.middleware — CSRF bypass and exception handling.

Covers:
  - CSRF disabled for /api/ endpoints
  - Exception handler returns JSON 500 for /api/ paths
  - Non-API paths are unaffected
"""
import pytest
from django.test import RequestFactory
from api.middleware import ApiMiddleware


class TestApiMiddleware:
    """Validates the REST API middleware behavior."""

    def setup_method(self):
        self.middleware = ApiMiddleware(get_response=lambda r: None)
        self.rf = RequestFactory()

    def test_csrf_disabled_for_api_paths(self):
        req = self.rf.get("/api/rag/status")
        self.middleware.process_request(req)
        assert hasattr(req, "_dont_enforce_csrf_checks")
        assert req._dont_enforce_csrf_checks is True

    def test_csrf_not_disabled_for_non_api_paths(self):
        req = self.rf.get("/admin/")
        self.middleware.process_request(req)
        assert not hasattr(req, "_dont_enforce_csrf_checks")

    def test_exception_handler_returns_json_for_api(self):
        req = self.rf.get("/api/rag/search")
        response = self.middleware.process_exception(req, Exception("Test error"))

        assert response is not None
        assert response.status_code == 500
        import json
        data = json.loads(response.content)
        assert "error" in data
        assert "Test error" in data["error"]

    def test_exception_handler_skips_non_api(self):
        req = self.rf.get("/admin/")
        response = self.middleware.process_exception(req, Exception("Test"))
        assert response is None  # Should not handle non-API exceptions
