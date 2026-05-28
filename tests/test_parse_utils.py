from __future__ import annotations

import sys
from typing import Any
from datetime import datetime, timezone
from unittest.mock import MagicMock

# homeassistant is not available in this test environment, so we must mock it
# before any code tries to import from it.
_ha_modules = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.area_registry",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.http",
    "homeassistant.helpers.storage",
]
for _mod in _ha_modules:
    sys.modules[_mod] = MagicMock()

from custom_components.ha_read_only.api import (
    _to_pattern_list,
    _parse_expires_at,
    _token_fields_from_request,
)


class TestToPatternList:
    def test_string_with_newlines(self) -> None:
        result = _to_pattern_list("sensor.temp\nsensor.humidity\nbinary_sensor.door")
        assert result == ["sensor.temp", "sensor.humidity", "binary_sensor.door"]

    def test_list_of_strings(self) -> None:
        result = _to_pattern_list([" sensor.temp ", "sensor.humidity", " binary_sensor.door "])
        assert result == ["sensor.temp", "sensor.humidity", "binary_sensor.door"]

    def test_none_returns_empty_list(self) -> None:
        assert _to_pattern_list(None) == []

    def test_empty_string_returns_empty_list(self) -> None:
        assert _to_pattern_list("") == []

    def test_empty_list_returns_empty_list(self) -> None:
        assert _to_pattern_list([]) == []

    def test_mixed_list_with_empty_strings_filters_them_out(self) -> None:
        result = _to_pattern_list(["sensor.temp", "", "sensor.humidity", "  ", "binary_sensor.door"])
        assert result == ["sensor.temp", "sensor.humidity", "binary_sensor.door"]

    def test_whitespace_only_entries_are_removed(self) -> None:
        result = _to_pattern_list("sensor.temp\n  \n\t\nsensor.humidity")
        assert result == ["sensor.temp", "sensor.humidity"]

    def test_leading_trailing_whitespace_is_trimmed(self) -> None:
        result = _to_pattern_list("  sensor.temp  ")
        assert result == ["sensor.temp"]

    def test_non_string_non_list_returns_empty_list(self) -> None:
        assert _to_pattern_list(123) == []
        assert _to_pattern_list(True) == []

    def test_list_with_non_string_items_skips_them(self) -> None:
        result = _to_pattern_list(["sensor.temp", 123, None, "sensor.humidity"])
        assert result == ["sensor.temp", "sensor.humidity"]


class TestParseExpiresAt:
    def test_none_returns_none(self) -> None:
        assert _parse_expires_at(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_expires_at("") is None

    def test_int_timestamp_returns_float(self) -> None:
        result = _parse_expires_at(1700000000)
        assert result == 1700000000.0
        assert isinstance(result, float)

    def test_float_timestamp_returns_float(self) -> None:
        result = _parse_expires_at(1700000000.5)
        assert result == 1700000000.5
        assert isinstance(result, float)

    def test_iso_datetime_string_returns_timestamp(self) -> None:
        result = _parse_expires_at("2026-12-31T23:59:59")
        expected = datetime(2026, 12, 31, 23, 59, 59).timestamp()
        assert result == expected

    def test_iso_string_with_z_returns_timestamp(self) -> None:
        result = _parse_expires_at("2026-12-31T23:59:59Z")
        expected = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp()
        assert result == expected

    def test_invalid_string_returns_none(self) -> None:
        assert _parse_expires_at("not-a-date") is None

    def test_zero_returns_zero(self) -> None:
        result = _parse_expires_at(0)
        assert result == 0.0

    def test_iso_string_with_timezone_offset(self) -> None:
        result = _parse_expires_at("2026-12-31T20:59:59-03:00")
        expected = datetime(2026, 12, 31, 20, 59, 59, tzinfo=timezone.utc).timestamp() + 3 * 3600
        assert result == expected

    def test_whitespace_string_returns_none(self) -> None:
        assert _parse_expires_at("   ") is None

    def test_negative_timestamp(self) -> None:
        result = _parse_expires_at(-1)
        assert result == -1.0


class TestTokenFieldsFromRequest:
    def test_full_data_dict_maps_correctly(self) -> None:
        data = {
            "name": "My Token",
            "domains": ["sensor", "binary_sensor"],
            "patterns": "sensor.temp\nsensor.humidity",
            "blocked_patterns": "sensor.secret*",
            "include_attributes": False,
            "expires_at": 1700000000,
            "areas": ["living_room"],
            "allowed_ips": "10.0.0.1\n10.0.0.2",
            "allowed_entities": ["light.kitchen"],
            "color": "#ff0000",
            "rate_limit_max_requests": 100,
            "rate_limit_window_value": 5,
            "rate_limit_window_unit": "minutes",
        }
        result = _token_fields_from_request(data)
        assert result["name"] == "My Token"
        assert result["domains"] == ["sensor", "binary_sensor"]
        assert result["patterns"] == "sensor.temp\nsensor.humidity"
        assert result["blocked_patterns"] == "sensor.secret*"
        assert result["include_attributes"] is False
        assert result["expires_at"] == 1700000000.0
        assert result["areas"] == ["living_room"]
        assert result["allowed_ips"] == ["10.0.0.1", "10.0.0.2"]
        assert result["allowed_entities"] == ["light.kitchen"]
        assert result["color"] == "#ff0000"
        assert result["rate_limit_max_requests"] == 100
        assert result["rate_limit_window_value"] == 5
        assert result["rate_limit_window_unit"] == "minutes"

    def test_empty_dict_uses_defaults(self) -> None:
        result = _token_fields_from_request({})
        assert result["name"] == "Unnamed"
        assert result["domains"] == []
        assert result["patterns"] == ""
        assert result["blocked_patterns"] == ""
        assert result["include_attributes"] is True
        assert result["expires_at"] is None
        assert result["areas"] == []
        assert result["allowed_ips"] == []
        assert result["allowed_entities"] == []
        assert result["color"] == ""
        assert result["rate_limit_max_requests"] is None
        assert result["rate_limit_window_value"] is None
        assert result["rate_limit_window_unit"] is None

    def test_partial_data_missing_fields_get_defaults(self) -> None:
        data = {"name": "Partial Token"}
        result = _token_fields_from_request(data)
        assert result["name"] == "Partial Token"
        assert result["domains"] == []
        assert result["patterns"] == ""
        assert result["blocked_patterns"] == ""
        assert result["include_attributes"] is True
        assert result["expires_at"] is None
        assert result["areas"] == []
        assert result["allowed_ips"] == []
        assert result["allowed_entities"] == []
        assert result["color"] == ""
        assert result["rate_limit_max_requests"] is None
        assert result["rate_limit_window_value"] is None
        assert result["rate_limit_window_unit"] is None

    def test_rate_limit_max_requests_as_string_converted_to_int(self) -> None:
        data = {"rate_limit_max_requests": "50", "rate_limit_window_value": "3", "rate_limit_window_unit": "hours"}
        result = _token_fields_from_request(data)
        assert result["rate_limit_max_requests"] == 50
        assert result["rate_limit_window_value"] == 3
        assert result["rate_limit_window_unit"] == "hours"

    def test_rate_limit_max_requests_as_none(self) -> None:
        data = {"rate_limit_max_requests": None}
        result = _token_fields_from_request(data)
        assert result["rate_limit_max_requests"] is None

    def test_expires_at_passed_through_parse_expires_at(self) -> None:
        data = {"expires_at": "2026-12-31T23:59:59"}
        result = _token_fields_from_request(data)
        expected = datetime(2026, 12, 31, 23, 59, 59).timestamp()
        assert result["expires_at"] == expected

    def test_expires_at_none_becomes_none(self) -> None:
        data = {"expires_at": None}
        result = _token_fields_from_request(data)
        assert result["expires_at"] is None

    def test_allowed_ips_passed_through_parse_ip_list(self) -> None:
        data = {"allowed_ips": "10.0.0.1\n10.0.0.2"}
        result = _token_fields_from_request(data)
        assert result["allowed_ips"] == ["10.0.0.1", "10.0.0.2"]

    def test_allowed_ips_empty_string(self) -> None:
        data = {"allowed_ips": ""}
        result = _token_fields_from_request(data)
        assert result["allowed_ips"] == []

    def test_rate_limit_window_value_as_string_converted_to_int(self) -> None:
        data = {"rate_limit_window_value": "10"}
        result = _token_fields_from_request(data)
        assert result["rate_limit_window_value"] == 10

    def test_rate_limit_window_unit_empty_string_becomes_none(self) -> None:
        data = {"rate_limit_window_unit": ""}
        result = _token_fields_from_request(data)
        assert result["rate_limit_window_unit"] is None

    def test_rate_limit_window_unit_present(self) -> None:
        data = {"rate_limit_window_unit": "days"}
        result = _token_fields_from_request(data)
        assert result["rate_limit_window_unit"] == "days"

    def test_include_attributes_defaults_to_true(self) -> None:
        result = _token_fields_from_request({})
        assert result["include_attributes"] is True

    def test_include_attributes_false(self) -> None:
        data = {"include_attributes": False}
        result = _token_fields_from_request(data)
        assert result["include_attributes"] is False
