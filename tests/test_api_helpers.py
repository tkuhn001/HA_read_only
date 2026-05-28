from __future__ import annotations

import hashlib
import time
import secrets
from unittest.mock import MagicMock

import pytest

from custom_components.ha_read_only.api import (
    _hash_token,
    _verify_token,
    _mask_token,
    _rate_limit_key,
    _build_response,
    _find_token_data,
    _get_client_ip,
)
from custom_components.ha_read_only.const import DOMAIN


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
