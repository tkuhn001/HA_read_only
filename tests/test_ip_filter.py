from __future__ import annotations

from typing import Any

import pytest

from custom_components.ha_read_only.api import (
    _ip_matches,
    _is_ip_allowed,
    _parse_ip_list,
)


class TestIpMatches:
    def test_exact_match(self) -> None:
        assert _ip_matches("10.0.0.1", "10.0.0.1") is True

    def test_no_match(self) -> None:
        assert _ip_matches("10.0.0.2", "10.0.0.1") is False

    def test_cidr_24_in_range(self) -> None:
        assert _ip_matches("10.0.0.50", "10.0.0.0/24") is True

    def test_cidr_24_out_of_range(self) -> None:
        assert _ip_matches("10.0.1.1", "10.0.0.0/24") is False

    def test_cidr_16(self) -> None:
        assert _ip_matches("10.0.255.255", "10.0.0.0/16") is True

    def test_cidr_32_single_ip(self) -> None:
        assert _ip_matches("192.168.1.1", "192.168.1.1/32") is True

    def test_invalid_allowed_ip_returns_false(self) -> None:
        assert _ip_matches("1.2.3.4", "not-an-ip") is False

    def test_ipv6_support(self) -> None:
        assert _ip_matches("::1", "::1/128") is True


class TestIsIpAllowed:
    def test_empty_list_allows_all(self) -> None:
        assert _is_ip_allowed("10.0.0.1", []) is True

    def test_client_ip_in_list(self) -> None:
        assert _is_ip_allowed("10.0.0.1", ["10.0.0.1", "10.0.0.2"]) is True

    def test_client_ip_not_in_list(self) -> None:
        assert _is_ip_allowed("10.0.0.3", ["10.0.0.1", "10.0.0.2"]) is False

    def test_cidr_in_list_client_in_range(self) -> None:
        assert _is_ip_allowed("10.0.0.50", ["10.0.0.0/24"]) is True

    def test_cidr_in_list_client_out_of_range(self) -> None:
        assert _is_ip_allowed("10.0.1.1", ["10.0.0.0/24"]) is False

    def test_multiple_entries_one_matches(self) -> None:
        assert _is_ip_allowed("192.168.1.1", ["10.0.0.0/8", "192.168.1.0/24", "172.16.0.0/12"]) is True


class TestParseIpList:
    def test_string_with_newlines(self) -> None:
        result = _parse_ip_list("10.0.0.1\n10.0.0.2\n10.0.0.3")
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_string_with_commas(self) -> None:
        result = _parse_ip_list("10.0.0.1, 10.0.0.2, 10.0.0.3")
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_string_with_mixed_commas_and_newlines(self) -> None:
        result = _parse_ip_list("10.0.0.1, 10.0.0.2\n10.0.0.3")
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_list_of_strings(self) -> None:
        result = _parse_ip_list([" 10.0.0.1 ", "10.0.0.2", " 10.0.0.3 "])
        assert result == ["10.0.0.1", "10.0.0.2", "10.0.0.3"]

    def test_empty_string(self) -> None:
        assert _parse_ip_list("") == []

    def test_none(self) -> None:
        assert _parse_ip_list(None) == []

    def test_empty_list(self) -> None:
        assert _parse_ip_list([]) == []
