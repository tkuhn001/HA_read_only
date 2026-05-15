# HA Read-Only API – Home Assistant Integration
# Copyright (c) 2026 T. Kuhn
# Version: 0.3.3 | Datum: 15. Mai 2026
# Lizenz: MIT – Siehe LICENSE-Datei im Repository
#
# DIE SOFTWARE WIRD "AS IS" BEREITGESTELLT, OHNE JEGLICHE GEWÄHRLEISTUNG.
# NUTZUNG AUF EIGENE GEFAHR.

import logging
import secrets
import voluptuous as vol
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import API_PREFIX, CONF_TOKEN, CONF_TOKEN_NAME, DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

class ReadOnlyDataHandler:
    """Manages the centralized storage for tokens and stats."""
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.data: dict = {
            "tokens": [],
            "stats": {},
            "config": {},
            "usage_log": [],
            "rate_limit": {},
        }

    async def async_load(self) -> None:
        """Load data from storage."""
        stored = await self.store.async_load()
        if stored:
            self.data = stored
        else:
            self.data = {
                "tokens": [],
                "stats": {},
                "config": {},
                "usage_log": [],
                "rate_limit": {},
            }

    async def async_save(self) -> None:
        """Save data to storage."""
        await self.store.async_save(self.data)

try:
    from .api import async_setup_api
    HAS_API = True
except ImportError as err:
    _LOGGER.warning("API module not available: %s", err)
    HAS_API = False

async def _register_sidebar_link(hass: HomeAssistant) -> None:
    """Register sidebar link using the built-in iframe panel."""
    try:
        from homeassistant.components.frontend import async_register_built_in_panel
        async_register_built_in_panel(
            hass,
            "iframe",
            sidebar_title="HA Read-Only",
            sidebar_icon="mdi:shield-lock",
            frontend_url_path="ha_readonly_app",
            require_admin=False,
            config={"url": "/api/ha_read_only/admin"},
        )
        _LOGGER.info("Sidebar iframe panel registered")
    except Exception as err:
        _LOGGER.error("Failed to register sidebar panel: %s", err)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Read-Only API from a config entry."""
    _LOGGER.info("--- HA Read-Only Setup START ---")
    try:
        data_handler = ReadOnlyDataHandler(hass)
        await data_handler.async_load()
        _LOGGER.info("Storage loaded successfully")
        
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN]["handler"] = data_handler
        hass.data[DOMAIN]["entry_id"] = entry.entry_id

        await _register_sidebar_link(hass)
        _LOGGER.info("Sidebar registration called")
        
        entry.configuration_url = "/api/ha_read_only/admin"
        _LOGGER.info("Configuration URL set: %s", entry.configuration_url)

        if HAS_API:
            await async_setup_api(hass)
            _LOGGER.info("API views registered")

        entry.async_on_unload(entry.add_update_listener(async_update_entry))
        _LOGGER.info("--- HA Read-Only Setup FINISHED ---")
        return True
    except Exception as err:
        _LOGGER.exception("CRITICAL ERROR during setup: %s", err)
        return False

async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    pass

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if DOMAIN in hass.data:
        hass.data.pop(DOMAIN)
    return True