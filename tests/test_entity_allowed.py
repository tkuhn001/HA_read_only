from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ha_read_only.api import _is_entity_allowed


_AREA_MAP = {
    "sensor.temperature": "area_living_room",
    "sensor.humidity": "area_bathroom",
    "light.living_room": "area_living_room",
    "light.kitchen": "area_kitchen",
    "switch.test_allowed": None,
    "switch.no_area": None,
    "sensor.secret_value": "area_secret",
    "binary_sensor.door": None,
}


@pytest.fixture(autouse=True)
def _mock_er():
    """Patch api.er so _get_entity_area returns controlled area IDs.

    Unknown entities return None to simulate missing registry entries.
    """
    with patch("custom_components.ha_read_only.api.er") as mock_er:
        registry = MagicMock()

        def async_get(entity_id):
            if entity_id not in _AREA_MAP:
                return None
            entry = MagicMock()
            entry.area_id = _AREA_MAP[entity_id]
            return entry

        registry.async_get = async_get
        mock_er.async_get.return_value = registry
        yield


class TestIsEntityAllowed:
    """Unit tests for _is_entity_allowed — the core access-control function."""

    def test_no_whitelist_all_allowed(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.anything", token_data, hass) is True
        assert _is_entity_allowed("light.foobar", token_data, hass) is True
        assert _is_entity_allowed("switch.test", token_data, hass) is True

    def test_domain_filter_match(self) -> None:
        token_data = {
            "domains": ["sensor"],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is True

    def test_domain_filter_no_match(self) -> None:
        token_data = {
            "domains": ["light"],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is False

    def test_allowed_entities_exact_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": ["sensor.temperature"],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is True

    def test_allowed_entities_no_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": ["light.kitchen"],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is False

    def test_pattern_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "light.*",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("light.kitchen", token_data, hass) is True

    def test_pattern_no_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "light.*",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is False

    def test_blocked_pattern_blocks(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "sensor.secret_*",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.secret_value", token_data, hass) is False

    def test_blocked_pattern_overrides_domain(self) -> None:
        token_data = {
            "domains": ["sensor"],
            "patterns": "",
            "blocked_patterns": "sensor.*",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is False

    def test_area_filter_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_living_room"],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is True

    def test_area_filter_no_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_kitchen"],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is False

    def test_multiple_domains(self) -> None:
        token_data = {
            "domains": ["sensor", "light"],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is True
        assert _is_entity_allowed("light.kitchen", token_data, hass) is True
        assert _is_entity_allowed("switch.test", token_data, hass) is False

    def test_multiple_patterns(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "light.*\nswitch.*",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("light.kitchen", token_data, hass) is True
        assert _is_entity_allowed("switch.test_allowed", token_data, hass) is True
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is False

    def test_allowed_entity_ignores_area(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_kitchen"],
            "allowed_entities": ["sensor.temperature"],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is True

    def test_entity_with_no_area_in_registry(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_living_room"],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.ghost", token_data, hass) is False

    def test_blocked_pattern_with_asterisk(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "sensor.*",
            "areas": [],
            "allowed_entities": [],
        }
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is False
        assert _is_entity_allowed("light.kitchen", token_data, hass) is True

    def test_empty_whitelist_vs_no_whitelist(self) -> None:
        hass = MagicMock()
        assert _is_entity_allowed("sensor.temperature", {}, hass) is True
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        assert _is_entity_allowed("sensor.temperature", token_data, hass) is True
