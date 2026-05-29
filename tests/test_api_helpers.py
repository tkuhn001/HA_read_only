from __future__ import annotations

import hashlib
import time
import secrets
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.ha_read_only.api import (
    _hash_token,
    _verify_token,
    _mask_token,
    _rate_limit_key,
    _build_response,
    _find_token_data,
    _get_client_ip,
    _fire_webhook,
    _track_usage,
    _check_versions,
)
from custom_components.ha_read_only.const import DOMAIN, CONF_WEBHOOK_URL, CONF_WEBHOOK_ON_API, CONF_WEBHOOK_ON_TOKEN, USAGE_LOG_MAX


# --- _hash_token ---


def test_hash_token_consistency():
    token = "my-secret-token"
    h1 = _hash_token(token)
    h2 = _hash_token(token)
    assert h1 == h2


def test_hash_token_different_inputs():
    assert _hash_token("token-a") != _hash_token("token-b")


def test_hash_token_empty_string():
    h = _hash_token("")
    assert isinstance(h, str)
    assert len(h) == 64
    assert h == hashlib.sha256(b"").hexdigest()


# --- _verify_token ---


def test_verify_token_correct():
    token = "valid-token"
    hashed = _hash_token(token)
    assert _verify_token(token, hashed) is True


def test_verify_token_wrong():
    hashed = _hash_token("real-token")
    assert _verify_token("wrong-token", hashed) is False


def test_verify_token_empty_plain():
    hashed = _hash_token("something")
    assert _verify_token("", hashed) is False


def test_verify_token_empty_hash():
    assert _verify_token("token", "") is False


def test_verify_token_both_empty():
    assert _verify_token("", _hash_token("")) is True


# --- _mask_token ---


def test_mask_token_longer_than_eight():
    assert _mask_token("1234567890") == "12345678..."
    assert _mask_token("abcdefghijklm") == "abcdefgh..."
    assert _mask_token("123456789") == "12345678..."


def test_mask_token_exactly_eight():
    assert _mask_token("12345678") == "12345678"


def test_mask_token_shorter_than_eight():
    assert _mask_token("abc") == "abc"
    assert _mask_token("") == ""
    assert _mask_token("a") == "a"


def test_mask_token_empty():
    assert _mask_token("") == ""


# --- _rate_limit_key ---


def test_rate_limit_key_ip():
    result = _rate_limit_key(("ip", "1.2.3.4"))
    assert result == "ip|1.2.3.4"


def test_rate_limit_key_token():
    result = _rate_limit_key(("token", "abc123"))
    assert result == "token|abc123"


# --- _build_response ---


def test_build_response_with_attrs():
    state = MagicMock()
    state.entity_id = "sensor.temperature"
    state.state = "22.5"
    state.attributes = {"unit_of_measurement": "°C", "friendly_name": "Temperature"}

    result = _build_response(state, include_attrs=True)
    assert result == {
        "entity_id": "sensor.temperature",
        "state": "22.5",
        "attributes": {"unit_of_measurement": "°C", "friendly_name": "Temperature"},
    }


def test_build_response_without_attrs():
    state = MagicMock()
    state.entity_id = "binary_sensor.door"
    state.state = "on"
    state.attributes = {"friendly_name": "Door"}

    result = _build_response(state, include_attrs=False)
    assert result == {
        "entity_id": "binary_sensor.door",
        "state": "on",
    }
    assert "attributes" not in result


def test_build_response_empty_attributes():
    state = MagicMock()
    state.entity_id = "switch.test"
    state.state = "off"
    state.attributes = {}

    result = _build_response(state, include_attrs=True)
    assert result == {
        "entity_id": "switch.test",
        "state": "off",
        "attributes": {},
    }


# --- _find_token_data ---


@pytest.fixture
def mock_hass_with_tokens():
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "handler": MagicMock(),
        }
    }
    token_value = "test-real-token"
    token_hash = _hash_token(token_value)
    handler = hass.data[DOMAIN]["handler"]
    handler.data = {
        "tokens": [
            {
                "id": "abc123",
                "token_hash": token_hash,
                "name": "Hashtoken",
            },
            {
                "id": "def456",
                "token": "plain-token-value",
                "name": "Plaintext-Token",
            },
        ]
    }
    return hass, token_value


def test_find_token_data_by_hash(mock_hass_with_tokens):
    hass, token_value = mock_hass_with_tokens
    result = _find_token_data(hass, token_value)
    assert result is not None
    assert result["id"] == "abc123"
    assert result["name"] == "Hashtoken"


def test_find_token_data_by_plaintext(mock_hass_with_tokens):
    hass, _ = mock_hass_with_tokens
    result = _find_token_data(hass, "plain-token-value")
    assert result is not None
    assert result["id"] == "def456"
    assert result["name"] == "Plaintext-Token"


def test_find_token_data_no_match(mock_hass_with_tokens):
    hass, _ = mock_hass_with_tokens
    result = _find_token_data(hass, "non-existent-token")
    assert result is None


def test_find_token_data_none(mock_hass_with_tokens):
    hass, _ = mock_hass_with_tokens
    result = _find_token_data(hass, None)
    assert result is None


def test_find_token_data_empty_string(mock_hass_with_tokens):
    hass, _ = mock_hass_with_tokens
    result = _find_token_data(hass, "")
    assert result is None


# --- _get_client_ip ---


def test_get_client_ip_from_x_forwarded_for():
    request = MagicMock()
    request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
    request.transport = MagicMock()

    ip = _get_client_ip(request)
    assert ip == "192.168.1.1"


def test_get_client_ip_from_peername():
    request = MagicMock()
    request.headers = {}
    request.transport.get_extra_info.return_value = ("10.0.0.5", 54321)

    ip = _get_client_ip(request)
    assert ip == "10.0.0.5"


def test_get_client_ip_unknown():
    request = MagicMock()
    request.headers = {}
    request.transport.get_extra_info.return_value = None

    ip = _get_client_ip(request)
    assert ip == "unknown"


# --- _fire_webhook ---


class TestFireWebhook:
    def _make_handler(self, url="http://hook.example.com", on_api=True, on_token=True):
        handler = MagicMock()
        handler.data = {
            "config": {
                CONF_WEBHOOK_URL: url,
                CONF_WEBHOOK_ON_API: on_api,
                CONF_WEBHOOK_ON_TOKEN: on_token,
            }
        }
        return handler

    async def test_sends_post_to_hook_url(self):
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("aiohttp.ClientSession.post") as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_post.return_value = mock_response
                await _fire_webhook(MagicMock(), "api_request", {"endpoint": "/states"})
                mock_post.assert_called_once()
                args, kwargs = mock_post.call_args
                assert args[0] == "http://hook.example.com"
                assert kwargs["json"]["event"] == "api_request"

    async def test_skips_when_url_empty(self):
        handler = self._make_handler(url="")
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("aiohttp.ClientSession.post") as mock_post:
                await _fire_webhook(MagicMock(), "api_request", {})
                mock_post.assert_not_called()

    async def test_skips_when_event_not_enabled(self):
        handler = self._make_handler(on_api=False)
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("aiohttp.ClientSession.post") as mock_post:
                await _fire_webhook(MagicMock(), "api_request", {})
                mock_post.assert_not_called()

    async def test_fires_on_token_created(self):
        handler = self._make_handler(on_token=True)
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("aiohttp.ClientSession.post") as mock_post:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_post.return_value = mock_response
                await _fire_webhook(MagicMock(), "token_created", {"token_name": "test"})
                mock_post.assert_called_once()

    async def test_logs_warning_on_http_error(self):
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("aiohttp.ClientSession.post") as mock_post:
                mock_response = AsyncMock()
                mock_response.__aenter__.return_value.status = 500
                mock_post.return_value = mock_response
                with patch("custom_components.ha_read_only.api._LOGGER.warning") as mock_log:
                    await _fire_webhook(MagicMock(), "api_request", {})
                    mock_log.assert_called_once_with("Webhook returned %s", 500)

    @pytest.mark.filterwarnings("ignore:coroutine.*AsyncMock")
    async def test_logs_warning_on_exception(self):
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("aiohttp.ClientSession") as mock_session_cls:
                mock_session = AsyncMock()
                mock_session.post.side_effect = Exception("timeout")
                mock_session_cls.return_value = mock_session
                with patch("custom_components.ha_read_only.api._LOGGER.warning") as mock_log:
                    await _fire_webhook(MagicMock(), "api_request", {})
                    mock_log.assert_called_once()


# --- _track_usage ---


class TestTrackUsage:
    def _make_handler(self, with_tokens=False):
        handler = MagicMock()
        handler.data = {
            "stats": {},
            "config": {"stats_log_max": 500, "stats_log_max_enabled": True},
            "usage_log": [],
            "invalid_log": [],
            "tokens": [],
        }
        handler.async_save = AsyncMock()
        return handler

    async def test_creates_new_stats_entry(self):
        hass = MagicMock()
        handler = self._make_handler()
        token_data = None
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=token_data):
                with patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()):
                    await _track_usage(hass, "tok_abc", "/states", 200, token_name="test", token_id="t1")
        stats = handler.data["stats"]
        assert "t1" in stats
        assert stats["t1"]["total"] == 1
        assert stats["t1"]["token_name"] == "test"
        assert stats["t1"]["by_endpoint"]["/states"] == 1
        assert stats["t1"]["errors"] == 0

    async def test_increments_existing_stats(self):
        hass = MagicMock()
        handler = self._make_handler()
        handler.data["stats"]["t1"] = {"total": 5, "by_endpoint": {"/help": 2}, "errors": 0, "last_access": None, "last_endpoint": None}
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=None):
                with patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()):
                    await _track_usage(hass, "tok_abc", "/states", 200, token_name="test", token_id="t1")
        assert handler.data["stats"]["t1"]["total"] == 6
        assert handler.data["stats"]["t1"]["by_endpoint"]["/states"] == 1

    async def test_counts_errors_on_4xx(self):
        hass = MagicMock()
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=None):
                with patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()):
                    await _track_usage(hass, "tok_abc", "/states", 401, token_id="t1")
        assert handler.data["stats"]["t1"]["errors"] == 1
        assert handler.data["stats"]["t1"]["last_endpoint"] == "/states"

    async def test_respects_global_max_limit(self):
        hass = MagicMock()
        handler = self._make_handler()
        handler.data["stats"]["t1"] = {"total": 500, "by_endpoint": {}, "errors": 0, "last_access": None, "last_endpoint": None}
        handler.data["config"] = {"stats_log_max": 500, "stats_log_max_enabled": True}
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=None):
                with patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()):
                    await _track_usage(hass, "tok_abc", "/states", 200, token_id="t1")
        assert handler.data["stats"]["t1"]["total"] == 500

    async def test_no_token_fallback_key(self):
        hass = MagicMock()
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=None):
                with patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()):
                    await _track_usage(hass, None, "/states", 200)
        key = "no_token"
        stats = handler.data["stats"]
        assert key in stats
        assert stats[key]["total"] == 1

    async def test_appends_to_usage_log(self):
        hass = MagicMock()
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=None):
                with patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()):
                    await _track_usage(hass, "tok_abc", "/states", 200, token_name="test", token_id="t1")
        assert len(handler.data["usage_log"]) == 1
        assert handler.data["usage_log"][0]["status"] == 200

    async def test_401_goes_to_invalid_log(self):
        hass = MagicMock()
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=None):
                with patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()):
                    await _track_usage(hass, "tok_bad", "/states", 401)
        assert len(handler.data["invalid_log"]) == 1
        assert handler.data["invalid_log"][0]["status"] == 401

    async def test_fires_webhook_on_200_with_token(self):
        hass = MagicMock()
        handler = self._make_handler()
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            with patch("custom_components.ha_read_only.api._find_token_data", return_value=None):
                with patch("custom_components.ha_read_only.api._fire_webhook", new_callable=AsyncMock) as mock_hook:
                    await _track_usage(hass, "tok_abc", "/states", 200, token_name="test")
                    mock_hook.assert_awaited_once_with(hass, "api_request", {"endpoint": "/states", "token_name": "test", "ip": ""})


# --- _check_versions ---


class TestCheckVersions:
    def test_logs_warning_on_mismatch(self):
        with patch("custom_components.ha_read_only.api.open") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = '{"version": "9.9.9"}'
            with patch("custom_components.ha_read_only.api._LOGGER.warning") as mock_log:
                _check_versions(MagicMock())
                mock_log.assert_called_once()

    def test_no_warning_on_match(self):
        with patch("custom_components.ha_read_only.api.open") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = '{"version": "0.4.2"}'
            with patch("custom_components.ha_read_only.api._LOGGER.warning") as mock_log:
                _check_versions(MagicMock())
                mock_log.assert_not_called()

    def test_logs_warning_on_io_error(self):
        with patch("custom_components.ha_read_only.api.open", side_effect=IOError("no file")):
            with patch("custom_components.ha_read_only.api._LOGGER.warning") as mock_log:
                _check_versions(MagicMock())
                mock_log.assert_called_once()
