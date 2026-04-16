"""
Tests for api.services.config — Application settings persistence layer.

Covers:
  - load/save app settings (defaults, merge, round-trip)
  - load/save LLM config
  - load/save cache
  - local file stats caching
  - Migration from old folder_config.json format
"""
import pytest
import json
from api.services.config import (
    load_app_settings, save_app_settings,
    load_llm_config, save_llm_config,
    load_cache, save_cache,
    load_local_stats_cache, save_local_stats_cache,
    load_folder_config, save_folder_config,
    _DEFAULT_APP_SETTINGS, _DEFAULT_LLM_CONFIG,
)


class TestAppSettings:
    """Validates app_settings.json persistence."""

    def test_load_returns_defaults_when_no_file(self, tmp_storage):
        result = load_app_settings()
        assert result == _DEFAULT_APP_SETTINGS

    def test_save_and_load_round_trip(self, tmp_storage):
        custom = {
            "cloud_enabled": False,
            "local_enabled": True,
            "local_root_path": "D:\\TestDocs",
            "drive_folder_id": "abc123",
            "drive_folder_name": "My Folder",
        }
        save_app_settings(custom)
        loaded = load_app_settings()
        assert loaded["cloud_enabled"] is False
        assert loaded["local_root_path"] == "D:\\TestDocs"
        assert loaded["drive_folder_id"] == "abc123"

    def test_load_merges_with_defaults(self, tmp_storage):
        """Partial settings file should be merged with defaults."""
        partial = {"cloud_enabled": False}
        (tmp_storage / "app_settings.json").write_text(
            json.dumps(partial), encoding="utf-8"
        )
        loaded = load_app_settings()
        assert loaded["cloud_enabled"] is False
        # Default keys should still be present
        assert "local_enabled" in loaded
        assert "local_root_path" in loaded


class TestLLMConfig:
    """Validates llm_config.json persistence."""

    def test_load_returns_defaults(self, tmp_storage):
        result = load_llm_config()
        assert result == _DEFAULT_LLM_CONFIG
        assert result["model"] == "llama3.2"

    def test_save_and_load(self, tmp_storage):
        cfg = {"base_url": "http://localhost:11434", "model": "mistral", "provider": "ollama"}
        save_llm_config(cfg)
        loaded = load_llm_config()
        assert loaded["model"] == "mistral"


class TestDriveCache:
    """Validates drive_cache.json persistence."""

    def test_load_returns_default_when_empty(self, tmp_storage):
        result = load_cache()
        assert result == {"files": [], "synced_at": None}

    def test_save_and_load_cache(self, tmp_storage):
        data = {"files": [{"id": "f1", "name": "test.docx"}], "synced_at": "2026-01-01"}
        save_cache(data)
        loaded = load_cache()
        assert len(loaded["files"]) == 1
        assert loaded["files"][0]["name"] == "test.docx"


class TestLocalStatsCache:
    """Validates local file statistics caching."""

    def test_load_returns_default_when_empty(self, tmp_storage):
        result = load_local_stats_cache()
        assert result == {"total": 0, "size": 0, "file_types": {}}

    def test_save_and_load_stats(self, tmp_storage):
        stats = {"total": 42, "size": 1024000, "file_types": {"pdf": 10, "docx": 32}}
        save_local_stats_cache(stats)
        loaded = load_local_stats_cache()
        assert loaded["total"] == 42
        assert loaded["file_types"]["pdf"] == 10


class TestFolderConfig:
    """Validates the deprecated folder_config → app_settings migration."""

    def test_save_folder_config_updates_app_settings(self, tmp_storage):
        save_folder_config("folder_abc", "My Research")
        settings = load_app_settings()
        assert settings["drive_folder_id"] == "folder_abc"
        assert settings["drive_folder_name"] == "My Research"

    def test_load_folder_config_from_app_settings(self, tmp_storage):
        save_app_settings({
            **_DEFAULT_APP_SETTINGS,
            "drive_folder_id": "xyz",
            "drive_folder_name": "Docs",
        })
        result = load_folder_config()
        assert result["folder_id"] == "xyz"
        assert result["folder_name"] == "Docs"

    def test_load_folder_config_returns_none_when_empty(self, tmp_storage):
        result = load_folder_config()
        assert result is None
