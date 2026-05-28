from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from custom_components.ha_read_only.api import _rate_limit
from custom_components.ha_read_only.const import (
    DOMAIN,
    RATE_LIMIT_WINDOW,
    RATE_LIMIT_MAX_PER_IP,
    RATE_LIMIT_MAX_PER_TOKEN,
)


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "handler": MagicMock(),
        }
    }
    handler = hass.data[DOMAIN]["handler"]
    handler.data = {
        "config": {},
        "rate_limit": {},
    }
    return hass


class TestRateLimit:
    """Tests for the _rate_limit function."""

    def test_under_limit_allowed(self, mock_hass):
        """A few requests under the limit should all be allowed."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_ip"] = 100

        for _ in range(5):
            result = _rate_limit(mock_hass, ("ip", "1.2.3.4"))
            assert result is True

    def test_over_limit_blocked(self, mock_hass):
        """Exceeding max_limit should block the request."""
        max_limit = 3
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_ip"] = max_limit

        for _ in range(max_limit):
            assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is True

        assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is False

    def test_window_expiry_allows_new_requests(self, mock_hass):
        """After rate limit window expires, requests should be allowed again."""
        max_limit = 3
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_ip"] = max_limit

        for _ in range(max_limit):
            assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is True

        assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is False

        cache = mock_hass.data[DOMAIN]["handler"].data["rate_limit"]
        cache_key = "ip|1.2.3.4"
        old_time = time.time() - 61
        cache[cache_key] = [old_time] * max_limit

        assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is True

    def test_ip_rate_limit(self, mock_hass):
        """IP-based rate limiting uses RATE_LIMIT_MAX_PER_IP."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_ip"] = RATE_LIMIT_MAX_PER_IP

        for _ in range(RATE_LIMIT_MAX_PER_IP):
            assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is True

        assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is False

    def test_token_rate_limit_default(self, mock_hass):
        """Token-based rate limiting uses RATE_LIMIT_MAX_PER_TOKEN by default."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_token"] = RATE_LIMIT_MAX_PER_TOKEN

        for _ in range(RATE_LIMIT_MAX_PER_TOKEN):
            assert _rate_limit(mock_hass, ("token", "test_token")) is True

        assert _rate_limit(mock_hass, ("token", "test_token")) is False

    def test_per_token_override_lower(self, mock_hass):
        """Per-token override with a lower limit applies correctly."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_token"] = 500

        token_data = {
            "rate_limit_max_requests": 3,
            "rate_limit_window_value": 60,
            "rate_limit_window_unit": "seconds",
        }

        for _ in range(3):
            assert _rate_limit(mock_hass, ("token", "limited_token"), token_data) is True

        assert _rate_limit(mock_hass, ("token", "limited_token"), token_data) is False

    def test_per_token_override_higher(self, mock_hass):
        """Per-token override with a higher limit applies correctly."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_token"] = 3

        token_data = {
            "rate_limit_max_requests": 10,
            "rate_limit_window_value": 60,
            "rate_limit_window_unit": "seconds",
        }

        for _ in range(10):
            assert _rate_limit(mock_hass, ("token", "generous_token"), token_data) is True

        assert _rate_limit(mock_hass, ("token", "generous_token"), token_data) is False

    def test_per_token_override_with_custom_window(self, mock_hass):
        """Per-token override with a custom window (e.g. 5 minutes) applies correctly."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_token"] = 500

        token_data = {
            "rate_limit_max_requests": 2,
            "rate_limit_window_value": 5,
            "rate_limit_window_unit": "minutes",
        }
        custom_window = 300

        assert _rate_limit(mock_hass, ("token", "window_token"), token_data) is True
        assert _rate_limit(mock_hass, ("token", "window_token"), token_data) is True
        assert _rate_limit(mock_hass, ("token", "window_token"), token_data) is False

        cache = mock_hass.data[DOMAIN]["handler"].data["rate_limit"]
        cache_key = "token|window_token"
        old_time = time.time() - custom_window - 1
        cache[cache_key] = [old_time] * 2

        assert _rate_limit(mock_hass, ("token", "window_token"), token_data) is True

    def test_ip_and_token_independent(self, mock_hass):
        """Rate limiting for IP and token are independent counters."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_ip"] = 3
        config["rate_limit_max_per_token"] = 5

        for _ in range(3):
            assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is True

        assert _rate_limit(mock_hass, ("ip", "1.2.3.4")) is False

        for _ in range(5):
            assert _rate_limit(mock_hass, ("token", "independent_token")) is True

        assert _rate_limit(mock_hass, ("token", "independent_token")) is False

    def test_multiple_tokens_independent(self, mock_hass):
        """Different tokens have separate rate limit counters."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_token"] = 3

        token_a_data = {
            "rate_limit_max_requests": 2,
            "rate_limit_window_value": 60,
            "rate_limit_window_unit": "seconds",
        }
        token_b_data = {
            "rate_limit_max_requests": 5,
            "rate_limit_window_value": 60,
            "rate_limit_window_unit": "seconds",
        }

        assert _rate_limit(mock_hass, ("token", "token_a"), token_a_data) is True
        assert _rate_limit(mock_hass, ("token", "token_a"), token_a_data) is True
        assert _rate_limit(mock_hass, ("token", "token_a"), token_a_data) is False

        for _ in range(5):
            assert _rate_limit(mock_hass, ("token", "token_b"), token_b_data) is True

        assert _rate_limit(mock_hass, ("token", "token_b"), token_b_data) is False

    def test_max_limit_one(self, mock_hass):
        """With rate_limit_max_requests=1, every second request is blocked."""
        config = mock_hass.data[DOMAIN]["handler"].data["config"]
        config["rate_limit_window"] = 60
        config["rate_limit_max_per_token"] = 500

        token_data = {
            "rate_limit_max_requests": 1,
            "rate_limit_window_value": 1,
            "rate_limit_window_unit": "minutes",
        }

        assert _rate_limit(mock_hass, ("token", "single_token"), token_data) is True
        assert _rate_limit(mock_hass, ("token", "single_token"), token_data) is False

        cache = mock_hass.data[DOMAIN]["handler"].data["rate_limit"]
        cache_key = "token|single_token"
        cache[cache_key] = [time.time() - 61]

        assert _rate_limit(mock_hass, ("token", "single_token"), token_data) is True
        assert _rate_limit(mock_hass, ("token", "single_token"), token_data) is False
