from __future__ import annotations

from unittest.mock import patch

from custom_components.ha_read_only.api import (
    _compute_daily_usage,
    _compute_hourly_charts,
)

_NOW = 1700000000
_HOUR = 3600


class TestHourlyChart:
    def _compute(self, entries):
        with patch("custom_components.ha_read_only.api.time.time", return_value=_NOW):
            return _compute_hourly_charts(entries, {})[0]

    def test_empty_log(self):
        assert self._compute([]) == [0] * 24

    def test_single_entry_current_hour(self):
        entry = {"timestamp": _NOW}
        result = self._compute([entry])
        assert result == [0] * 23 + [1]

    def test_single_entry_one_hour_ago(self):
        entry = {"timestamp": _NOW - _HOUR}
        result = self._compute([entry])
        assert result == [0] * 22 + [1] + [0]

    def test_multiple_entries_different_hours(self):
        entries = [
            {"timestamp": _NOW},
            {"timestamp": _NOW - _HOUR},
            {"timestamp": _NOW - 2 * _HOUR},
            {"timestamp": _NOW - 2 * _HOUR},
        ]
        result = self._compute(entries)
        assert result == [0] * 21 + [2] + [1] + [1]

    def test_entry_older_than_24h_ignored(self):
        entry = {"timestamp": _NOW - 86401}
        result = self._compute([entry])
        assert result == [0] * 24

    def test_entry_exactly_24h_included(self):
        entry = {"timestamp": _NOW - 86400}
        result = self._compute([entry])
        assert result == [0] * 23 + [1]

    def test_entry_without_timestamp_ignored(self):
        entry = {"foo": "bar"}
        result = self._compute([entry])
        assert result == [0] * 24

    def test_entry_with_none_timestamp_ignored(self):
        entry = {"timestamp": None}
        result = self._compute([entry])
        assert result == [0] * 24


class TestHourlyChartByColor:
    TOKENS = {
        "token_red": {"color": "red"},
        "token_blue": {"color": "blue"},
        "token_no_color": {},
    }

    def _make_buckets(self, *entries):
        with patch("custom_components.ha_read_only.api.time.time", return_value=_NOW):
            return _compute_hourly_charts(list(entries), self.TOKENS)[1]

    def test_empty_log(self):
        result = self._make_buckets()
        assert len(result) == 24
        for bucket in result:
            assert bucket == {"total": 0, "by_color": {}}

    def test_single_entry_known_color(self):
        entry = {"timestamp": _NOW, "token_id": "token_red"}
        result = self._make_buckets(entry)
        assert result[23] == {"total": 1, "by_color": {"red": 1}}
        for i in range(23):
            assert result[i] == {"total": 0, "by_color": {}}

    def test_unknown_token_id_defaults_to_default(self):
        entry = {"timestamp": _NOW, "token_id": "unknown"}
        result = self._make_buckets(entry)
        assert result[23] == {"total": 1, "by_color": {"_default": 1}}

    def test_token_without_color_defaults_to_default(self):
        entry = {"timestamp": _NOW, "token_id": "token_no_color"}
        result = self._make_buckets(entry)
        assert result[23] == {"total": 1, "by_color": {"_default": 1}}

    def test_multiple_colors_in_same_hour(self):
        entries = [
            {"timestamp": _NOW, "token_id": "token_red"},
            {"timestamp": _NOW, "token_id": "token_blue"},
            {"timestamp": _NOW, "token_id": "token_red"},
        ]
        result = self._make_buckets(*entries)
        assert result[23] == {"total": 3, "by_color": {"red": 2, "blue": 1}}

    def test_different_hours_different_colors(self):
        entries = [
            {"timestamp": _NOW, "token_id": "token_red"},
            {"timestamp": _NOW - _HOUR, "token_id": "token_blue"},
        ]
        result = self._make_buckets(*entries)
        assert result[23] == {"total": 1, "by_color": {"red": 1}}
        assert result[22] == {"total": 1, "by_color": {"blue": 1}}

    def test_old_entry_ignored(self):
        entry = {"timestamp": _NOW - 86401, "token_id": "token_red"}
        result = self._make_buckets(entry)
        for bucket in result:
            assert bucket == {"total": 0, "by_color": {}}

    def test_entry_without_timestamp_ignored(self):
        entry = {"token_id": "token_red"}
        result = self._make_buckets(entry)
        for bucket in result:
            assert bucket == {"total": 0, "by_color": {}}

    def test_entry_without_token_id_defaults_to_default(self):
        entry = {"timestamp": _NOW}
        result = self._make_buckets(entry)
        assert result[23] == {"total": 1, "by_color": {"_default": 1}}


class TestDailyUsage:
    def _compute(self, *entries):
        with patch("custom_components.ha_read_only.api.time.time", return_value=_NOW):
            return _compute_daily_usage(list(entries))

    def test_empty_log(self):
        assert self._compute() == {}

    def test_single_entry_today(self):
        entry = {"timestamp": _NOW, "token_id": "token_a"}
        result = self._compute(entry)
        assert result == {"token_a": [0, 0, 0, 0, 0, 0, 1]}

    def test_single_entry_one_day_ago(self):
        entry = {"timestamp": _NOW - 86400, "token_id": "token_a"}
        result = self._compute(entry)
        assert result == {"token_a": [0, 0, 0, 0, 0, 1, 0]}

    def test_single_entry_six_days_ago(self):
        entry = {"timestamp": _NOW - 6 * 86400, "token_id": "token_a"}
        result = self._compute(entry)
        assert result == {"token_a": [1, 0, 0, 0, 0, 0, 0]}

    def test_multiple_entries_same_token(self):
        entries = [
            {"timestamp": _NOW, "token_id": "token_a"},
            {"timestamp": _NOW - 86400, "token_id": "token_a"},
        ]
        result = self._compute(*entries)
        assert result == {"token_a": [0, 0, 0, 0, 0, 1, 1]}

    def test_different_tokens(self):
        entries = [
            {"timestamp": _NOW, "token_id": "token_a"},
            {"timestamp": _NOW, "token_id": "token_b"},
        ]
        result = self._compute(*entries)
        assert result == {
            "token_a": [0, 0, 0, 0, 0, 0, 1],
            "token_b": [0, 0, 0, 0, 0, 0, 1],
        }

    def test_entry_older_than_7_days_ignored(self):
        entry = {"timestamp": _NOW - 7 * 86400 - 1, "token_id": "token_a"}
        assert self._compute(entry) == {}

    def test_entry_exactly_7_days_included(self):
        entry = {"timestamp": _NOW - 7 * 86400, "token_id": "token_a"}
        result = self._compute(entry)
        assert result == {"token_a": [1, 0, 0, 0, 0, 0, 0]}

    def test_entry_without_token_id_ignored(self):
        entry = {"timestamp": _NOW}
        assert self._compute(entry) == {}

    def test_entry_with_empty_token_id_ignored(self):
        entry = {"timestamp": _NOW, "token_id": ""}
        assert self._compute(entry) == {}

    def test_entry_without_timestamp_ignored(self):
        entry = {"token_id": "token_a"}
        assert self._compute(entry) == {}
