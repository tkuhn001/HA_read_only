from __future__ import annotations

from unittest.mock import MagicMock

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
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.anything", token_data, area_map) is True
        assert _is_entity_allowed("light.foobar", token_data, area_map) is True
        assert _is_entity_allowed("switch.test", token_data, area_map) is True

    def test_domain_filter_match(self) -> None:
        token_data = {
            "domains": ["sensor"],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is True

    def test_domain_filter_no_match(self) -> None:
        token_data = {
            "domains": ["light"],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is False

    def test_allowed_entities_exact_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": ["sensor.temperature"],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is True

    def test_allowed_entities_no_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": ["light.kitchen"],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is False

    def test_pattern_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "light.*",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("light.kitchen", token_data, area_map) is True

    def test_pattern_no_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "light.*",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is False

    def test_blocked_pattern_blocks(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "sensor.secret_*",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.secret_value", token_data, area_map) is False

    def test_blocked_pattern_overrides_domain(self) -> None:
        token_data = {
            "domains": ["sensor"],
            "patterns": "",
            "blocked_patterns": "sensor.*",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is False

    def test_area_filter_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_living_room"],
            "allowed_entities": [],
        }
        assert _is_entity_allowed("sensor.temperature", token_data, _AREA_MAP) is True

    def test_area_filter_no_match(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_kitchen"],
            "allowed_entities": [],
        }
        assert _is_entity_allowed("sensor.temperature", token_data, _AREA_MAP) is False

    def test_multiple_domains(self) -> None:
        token_data = {
            "domains": ["sensor", "light"],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is True
        assert _is_entity_allowed("light.kitchen", token_data, area_map) is True
        assert _is_entity_allowed("switch.test", token_data, area_map) is False

    def test_multiple_patterns(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "light.*\nswitch.*",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("light.kitchen", token_data, area_map) is True
        assert _is_entity_allowed("switch.test_allowed", token_data, area_map) is True
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is False

    def test_allowed_entity_ignores_area(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_kitchen"],
            "allowed_entities": ["sensor.temperature"],
        }
        assert _is_entity_allowed("sensor.temperature", token_data, _AREA_MAP) is True

    def test_entity_with_no_area_in_registry(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": ["area_living_room"],
            "allowed_entities": [],
        }
        assert _is_entity_allowed("sensor.ghost", token_data, _AREA_MAP) is False

    def test_blocked_pattern_with_asterisk(self) -> None:
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "sensor.*",
            "areas": [],
            "allowed_entities": [],
        }
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is False
        assert _is_entity_allowed("light.kitchen", token_data, area_map) is True

    def test_empty_whitelist_vs_no_whitelist(self) -> None:
        area_map: dict[str, str | None] = {}
        assert _is_entity_allowed("sensor.temperature", {}, area_map) is True
        token_data = {
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }
        assert _is_entity_allowed("sensor.temperature", token_data, area_map) is True
