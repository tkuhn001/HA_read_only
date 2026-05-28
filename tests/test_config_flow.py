from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.ha_read_only.config_flow import (
    HaReadOnlyConfigFlow,
    HaReadOnlyOptionsFlow,
)
from custom_components.ha_read_only.const import DOMAIN


class TestHaReadOnlyConfigFlow:
    @pytest.mark.asyncio
    async def test_initial_step_shows_form(self):
        flow = HaReadOnlyConfigFlow()
        flow._async_current_entries = MagicMock(return_value=[])

        result = await flow.async_step_user(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_user_input_creates_entry(self):
        flow = HaReadOnlyConfigFlow()
        flow._async_current_entries = MagicMock(return_value=[])

        result = await flow.async_step_user(user_input={})

        assert result["type"] == "create_entry"
        assert result["title"] == "HA Read-Only API"
        assert result["data"] == {}

    @pytest.mark.asyncio
    async def test_already_configured_aborts(self):
        flow = HaReadOnlyConfigFlow()
        flow._async_current_entries = MagicMock(return_value=["existing_entry"])

        result = await flow.async_step_user(user_input=None)

        assert result["type"] == "abort"
        assert result["reason"] == "already_configured"

    def test_version_is_one(self):
        assert HaReadOnlyConfigFlow.VERSION == 1

    def test_domain_matches_const(self):
        from custom_components.ha_read_only.const import DOMAIN
        assert DOMAIN == "ha_read_only"

    def test_async_get_options_flow(self):
        config_entry = MagicMock()
        flow = HaReadOnlyConfigFlow.async_get_options_flow(config_entry)
        assert isinstance(flow, HaReadOnlyOptionsFlow)


class TestHaReadOnlyOptionsFlow:
    @pytest.mark.asyncio
    async def test_init_step_shows_form(self):
        config_entry = MagicMock()
        flow = HaReadOnlyOptionsFlow(config_entry)

        result = await flow.async_step_init(user_input=None)

        assert result["type"] == "form"
        assert result["step_id"] == "init"
