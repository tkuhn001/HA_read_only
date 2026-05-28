from __future__ import annotations

import time
import secrets
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from typing import Any

import pytest

from custom_components.ha_read_only.const import DOMAIN
from custom_components.ha_read_only.api import _hash_token


@pytest.fixture
def mock_hass():
    """Create a minimal mock HomeAssistant with handler structure."""
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "handler": MagicMock(),
            "entry_id": "test_entry",
        }
    }
    handler = hass.data[DOMAIN]["handler"]
    handler.data = {
        "tokens": [],
        "stats": {},
        "config": {},
        "usage_log": [],
        "rate_limit": {},
        "invalid_log": [],
    }
    handler.async_save = AsyncMock()
    return hass


@pytest.fixture
def sample_token_data():
    """Create sample token data for testing."""
    return {
        "id": secrets.token_hex(4),
        "token_hash": _hash_token("test-token-value"),
        "name": "Test Token",
        "created_at": time.time(),
        "domains": ["sensor", "binary_sensor"],
        "patterns": "light.*",
        "blocked_patterns": "sensor.secret_*",
        "include_attributes": True,
        "expires_at": None,
        "areas": ["area_living_room"],
        "allowed_ips": [],
        "allowed_entities": ["switch.test_allowed"],
        "color": "blue",
        "rate_limit_max_requests": None,
        "rate_limit_window_value": None,
        "rate_limit_window_unit": None,
    }


@pytest.fixture
def mock_entity_registry():
    """Create a mock entity registry with area mapping."""
    registry = MagicMock()
    entity_map = {
        "sensor.temperature": MagicMock(area_id="area_living_room"),
        "sensor.humidity": MagicMock(area_id="area_bathroom"),
        "light.living_room": MagicMock(area_id="area_living_room"),
        "light.kitchen": MagicMock(area_id="area_kitchen"),
        "switch.test_allowed": MagicMock(area_id=None),
        "switch.no_area": MagicMock(area_id=None),
        "sensor.secret_value": MagicMock(area_id="area_secret"),
        "binary_sensor.door": MagicMock(area_id=None),
    }

    def async_get(entity_id):
        return entity_map.get(entity_id)

    registry.async_get = async_get
    return registry


@pytest.fixture
def mock_area_registry():
    """Create a mock area registry."""
    registry = MagicMock()
    area_map = {
        "area_living_room": MagicMock(id="area_living_room", name="Living Room"),
        "area_bathroom": MagicMock(id="area_bathroom", name="Bathroom"),
        "area_kitchen": MagicMock(id="area_kitchen", name="Kitchen"),
        "area_secret": MagicMock(id="area_secret", name="Secret"),
    }

    def async_get_area(area_id):
        return area_map.get(area_id)

    registry.async_get_area = async_get_area
    return registry


@pytest.fixture
def mock_state():
    """Create a mock state object."""
    def _make(entity_id, state, attrs=None):
        s = MagicMock()
        s.entity_id = entity_id
        s.state = state
        s.attributes = attrs or {}
        return s
    return _make


@pytest.fixture
def mock_request():
    """Create a mock aiohttp request."""
    def _make(headers=None, peer=None, method="GET", path="/"):
        req = MagicMock()
        req.headers = headers or {}
        req.method = method
        req.path = path
        transport = MagicMock()
        transport.get_extra_info.return_value = peer
        req.transport = transport
        return req
    return _make


@pytest.fixture
def hass_with_tokens(mock_hass, sample_token_data):
    """Fixture with a populated token list."""
    handler = mock_hass.data[DOMAIN]["handler"]
    token1 = {**sample_token_data}
    token2 = {
        **sample_token_data,
        "id": secrets.token_hex(4),
        "name": "Second Token",
        "domains": ["light"],
        "patterns": "",
        "blocked_patterns": "",
        "areas": [],
        "allowed_entities": [],
        "color": "red",
    }
    handler.data["tokens"] = [token1, token2]
    return mock_hass, token1, token2
