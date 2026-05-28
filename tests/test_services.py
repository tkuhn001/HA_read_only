from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pytest

from custom_components.ha_read_only import _register_services
from custom_components.ha_read_only.const import DOMAIN
from custom_components.ha_read_only.api import _hash_token


@pytest.fixture
def handler_with_tokens():
    handler = MagicMock()
    handler.data = {
        "tokens": [
            {
                "id": "tok1",
                "name": "Wetterdienst",
                "token_hash": _hash_token("secret-token-1"),
                "created_at": 1000000.0,
                "expires_at": None,
                "domains": ["sensor", "weather"],
                "areas": [],
                "allowed_ips": [],
                "color": "blue",
            },
            {
                "id": "tok2",
                "name": "Lichtsteuerung",
                "token_hash": _hash_token("secret-token-2"),
                "created_at": 2000000.0,
                "expires_at": 9999999999.0,
                "domains": ["light"],
                "areas": ["area_living_room"],
                "allowed_ips": ["10.0.0.0/24"],
                "color": "red",
                "patterns": "",
                "blocked_patterns": "",
                "allowed_entities": [],
                "include_attributes": False,
                "rate_limit_max_requests": 50,
                "rate_limit_window_value": 1,
                "rate_limit_window_unit": "minutes",
                "stats_retention_days": 7,
                "regeneration_count": 2,
            },
        ],
        "stats": {},
        "config": {},
        "usage_log": [],
        "rate_limit": {},
    }
    return handler


@pytest.fixture
def mock_hass(handler_with_tokens):
    hass = MagicMock()
    hass.data = {DOMAIN: {"handler": handler_with_tokens}}
    hass.services.async_register = MagicMock()
    return hass


class TestServiceRegistration:
    async def test_registers_list_tokens(self, mock_hass):
        await _register_services(mock_hass)
        mock_hass.services.async_register.assert_any_call(
            DOMAIN, "list_tokens", unittest.mock.ANY
        )

    async def test_registers_get_token_info(self, mock_hass):
        await _register_services(mock_hass)
        mock_hass.services.async_register.assert_any_call(
            DOMAIN, "get_token_info", unittest.mock.ANY, schema=unittest.mock.ANY
        )

    async def test_get_token_info_has_schema(self, mock_hass):
        await _register_services(mock_hass)
        for args, kwargs in mock_hass.services.async_register.call_args_list:
            if args[1] == "get_token_info":
                schema = kwargs.get("schema")
                assert schema is not None
                assert "token_name" in schema.schema


class TestServiceLogic:
    @pytest.fixture(autouse=True)
    async def setup(self, mock_hass):
        await _register_services(mock_hass)
        self.hass = mock_hass

    def _get_handler(self, service_name):
        for args, kwargs in self.hass.services.async_register.call_args_list:
            if args[1] == service_name:
                return args[2]
        return None

    async def test_list_tokens_returns_count_and_tokens(self):
        handler = self._get_handler("list_tokens")
        call = MagicMock()
        result = await handler(call)
        assert result["count"] == 2
        assert len(result["tokens"]) == 2

    async def test_list_tokens_contains_token_names(self):
        handler = self._get_handler("list_tokens")
        call = MagicMock()
        result = await handler(call)
        assert result["tokens"][0]["name"] == "Wetterdienst"
        assert result["tokens"][1]["name"] == "Lichtsteuerung"

    async def test_list_tokens_masks_hash_values(self):
        handler = self._get_handler("list_tokens")
        call = MagicMock()
        result = await handler(call)
        for t in result["tokens"]:
            assert "..." in t["token_masked"]
            assert len(t["token_masked"]) == 11

    async def test_list_tokens_includes_id_and_color(self):
        handler = self._get_handler("list_tokens")
        call = MagicMock()
        result = await handler(call)
        token = result["tokens"][0]
        assert token["id"] == "tok1"
        assert token["color"] == "blue"
        assert token["created_at"] == 1000000.0
        assert token["expires_at"] is None

    async def test_get_token_info_found(self):
        handler = self._get_handler("get_token_info")
        call = MagicMock()
        call.data = {"token_name": "Wetterdienst"}
        result = await handler(call)
        assert result["found"] is True
        assert result["id"] == "tok1"
        assert result["name"] == "Wetterdienst"

    async def test_get_token_info_not_found(self):
        handler = self._get_handler("get_token_info")
        call = MagicMock()
        call.data = {"token_name": "NonExistent"}
        result = await handler(call)
        assert result["found"] is False
        assert result["error"] == "Token not found"

    async def test_get_token_info_case_insensitive(self):
        handler = self._get_handler("get_token_info")
        call = MagicMock()
        call.data = {"token_name": "wetterdienst"}
        result = await handler(call)
        assert result["found"] is True
        assert result["name"] == "Wetterdienst"

    async def test_get_token_info_with_all_fields(self):
        handler = self._get_handler("get_token_info")
        call = MagicMock()
        call.data = {"token_name": "Lichtsteuerung"}
        result = await handler(call)
        assert result["rate_limit_max_requests"] == 50
        assert result["rate_limit_window_unit"] == "minutes"
        assert result["regeneration_count"] == 2
        assert result["allowed_ips"] == ["10.0.0.0/24"]
