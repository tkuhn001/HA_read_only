from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ha_read_only.__init__ import ReadOnlyDataHandler
from custom_components.ha_read_only.const import STORAGE_KEY, STORAGE_VERSION


NOW = 1_000_000_000.0
DAY = 86400


@pytest.fixture
def handler():
    """Create ReadOnlyDataHandler with mocked store."""
    hass = MagicMock()
    h = ReadOnlyDataHandler(hass)
    h.store = AsyncMock()
    return h


class TestReadOnlyDataHandler:
    """Tests for basic ReadOnlyDataHandler operations."""

    def test_init_sets_default_data(self):
        """After init, data has expected keys with defaults."""
        hass = MagicMock()
        h = ReadOnlyDataHandler(hass)
        assert h.data == {
            "tokens": [],
            "stats": {},
            "config": {},
            "usage_log": [],
            "rate_limit": {},
        }

    async def test_async_load_with_stored_data(self, handler):
        """When store has data, it's loaded correctly."""
        stored = {
            "tokens": [{"id": "t1", "name": "Token 1"}],
            "stats": {"total_requests": 100},
            "config": {"stats_retention_days": 60},
            "usage_log": [{"timestamp": NOW, "path": "/api/test"}],
            "rate_limit": {"ip:1.2.3.4": {"count": 5}},
        }
        handler.store.async_load.return_value = stored
        await handler.async_load()
        assert handler.data == stored

    async def test_async_load_empty_store(self, handler):
        """When store returns None, defaults are set."""
        handler.store.async_load.return_value = None
        await handler.async_load()
        assert handler.data == {
            "tokens": [],
            "stats": {},
            "config": {},
            "usage_log": [],
            "rate_limit": {},
        }

    async def test_async_save_calls_store(self, handler):
        """async_save calls store.async_save with current data."""
        handler.data = {"tokens": [], "stats": {}, "config": {}, "usage_log": [], "rate_limit": {}}
        await handler.async_save()
        handler.store.async_save.assert_awaited_once_with(handler.data)

    async def test_async_save_runs_cleanup_first(self, handler):
        """async_save runs _cleanup_stats when run_cleanup=True."""
        with patch.object(handler, "_cleanup_stats") as mock_cleanup:
            await handler.async_save(run_cleanup=True)
            mock_cleanup.assert_awaited_once()
            handler.store.async_save.assert_awaited_once_with(handler.data)


class TestCleanupStats:
    """Tests for _cleanup_stats retention and limit logic."""

    @pytest.fixture
    def clean_handler(self, handler):
        """Handler with clean default data for cleanup tests."""
        handler.data = {
            "tokens": [],
            "stats": {},
            "config": {},
            "usage_log": [],
            "rate_limit": {},
        }
        return handler

    def _patch_time(self):
        return patch("custom_components.ha_read_only.__init__.time.time", return_value=NOW)

    async def test_cleanup_removes_old_entries(self, clean_handler):
        """Entries older than retention_days are removed."""
        clean_handler.data["config"] = {"stats_retention_days": 30}
        clean_handler.data["usage_log"] = [
            {"timestamp": NOW - (31 * DAY), "path": "/old"},
            {"timestamp": NOW - (29 * DAY), "path": "/new"},
            {"timestamp": NOW - (1 * DAY), "path": "/recent"},
        ]
        with self._patch_time():
            await clean_handler._cleanup_stats()
        paths = [e["path"] for e in clean_handler.data["usage_log"]]
        assert paths == ["/new", "/recent"]

    async def test_cleanup_respects_log_max(self, clean_handler):
        """Usage log is truncated to log_max."""
        clean_handler.data["config"] = {
            "stats_retention_enabled": False,
            "stats_log_max": 10,
        }
        clean_handler.data["usage_log"] = [
            {"timestamp": NOW - (i * DAY)} for i in range(50)
        ]
        with self._patch_time():
            await clean_handler._cleanup_stats()
        assert len(clean_handler.data["usage_log"]) == 10

    async def test_cleanup_retention_disabled(self, clean_handler):
        """When retention is disabled, old entries stay."""
        clean_handler.data["config"] = {
            "stats_retention_enabled": False,
            "stats_log_max_enabled": False,
        }
        clean_handler.data["usage_log"] = [
            {"timestamp": NOW - (365 * DAY), "path": "/very-old"},
            {"timestamp": NOW - (1 * DAY), "path": "/recent"},
        ]
        with self._patch_time():
            await clean_handler._cleanup_stats()
        assert len(clean_handler.data["usage_log"]) == 2

    async def test_cleanup_log_max_disabled(self, clean_handler):
        """When log_max is disabled, no truncation."""
        clean_handler.data["config"] = {
            "stats_retention_enabled": False,
            "stats_log_max_enabled": False,
            "stats_log_max": 500,
        }
        clean_handler.data["usage_log"] = [
            {"timestamp": NOW, "path": f"/entry-{i}"} for i in range(150)
        ]
        with self._patch_time():
            await clean_handler._cleanup_stats()
        assert len(clean_handler.data["usage_log"]) == 150

    async def test_cleanup_moves_401_to_invalid_log(self, clean_handler):
        """401 responses are moved to invalid_log."""
        clean_handler.data["config"] = {
            "stats_retention_enabled": False,
            "stats_log_max_enabled": False,
        }
        clean_handler.data["usage_log"] = [
            {"timestamp": NOW, "path": "/good", "status": 200},
            {"timestamp": NOW, "path": "/unauth", "status": 401},
            {"timestamp": NOW, "path": "/other", "status": 200},
        ]
        with self._patch_time():
            await clean_handler._cleanup_stats()
        assert clean_handler.data["usage_log"] == [
            {"timestamp": NOW, "path": "/good", "status": 200},
            {"timestamp": NOW, "path": "/other", "status": 200},
        ]
        assert clean_handler.data["invalid_log"] == [
            {"timestamp": NOW, "path": "/unauth", "status": 401},
        ]

    async def test_cleanup_per_token_retention(self, clean_handler):
        """Per-token retention overrides global."""
        token_id = "tok_1"
        clean_handler.data["tokens"] = [
            {"id": token_id, "name": "Short Retention Token", "stats_retention_days": 7},
            {"id": "tok_2", "name": "Default Token"},
        ]
        clean_handler.data["config"] = {"stats_retention_days": 30}
        clean_handler.data["usage_log"] = [
            {"timestamp": NOW - (15 * DAY), "token_id": token_id},
            {"timestamp": NOW - (15 * DAY), "token_id": "tok_2"},
            {"timestamp": NOW - (5 * DAY), "token_id": token_id},
            {"timestamp": NOW, "token_id": None},
        ]
        with self._patch_time():
            await clean_handler._cleanup_stats()
        assert len(clean_handler.data["usage_log"]) == 3

    async def test_cleanup_empty_log(self, clean_handler):
        """Empty log doesn't cause errors."""
        clean_handler.data["usage_log"] = []
        with self._patch_time():
            await clean_handler._cleanup_stats()
        assert clean_handler.data["usage_log"] == []
        assert clean_handler.data.get("invalid_log", None) is not None
        assert clean_handler.data["invalid_log"] == []

    async def test_cleanup_no_config(self, clean_handler):
        """When no config is set, defaults are used."""
        clean_handler.data["usage_log"] = [
            {"timestamp": NOW - (29 * DAY), "path": "/recent"},
            {"timestamp": NOW - (31 * DAY), "path": "/old"},
        ]
        with self._patch_time():
            await clean_handler._cleanup_stats()
        paths = [e["path"] for e in clean_handler.data["usage_log"]]
        assert paths == ["/recent"]
