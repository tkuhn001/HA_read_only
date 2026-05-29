# HA Read-Only API – Home Assistant Integration
# Copyright (c) 2026 T. Kuhn
# Lizenz: MIT – Siehe LICENSE-Datei im Repository
#
# DIE SOFTWARE WIRD "AS IS" BEREITGESTELLT, OHNE JEGLICHE GEWÄHRLEISTUNG.
# NUTZUNG AUF EIGENE GEFAHR.

import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

SERVICE_LIST_TOKENS = "list_tokens"
SERVICE_GET_TOKEN_INFO = "get_token_info"

SERVICE_GET_TOKEN_INFO_SCHEMA = vol.Schema({
    vol.Required("token_name"): cv.string,
})

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
        stored: dict | None = await self.store.async_load()
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
        await self._cleanup_stats()
        await self.store.async_save(self.data)

    async def _cleanup_stats(self) -> None:
        """Apply retention and limit rules to usage_log and stats."""
        config: dict = self.data.get("config", {})
        now = time.time()

        retention_enabled = config.get("stats_retention_enabled", True)
        retention_days = config.get("stats_retention_days", 30)
        log_max_enabled = config.get("stats_log_max_enabled", True)
        log_max = config.get("stats_log_max", 500)

        usage_log = self.data.get("usage_log", [])
        token_map = {t["id"]: t for t in self.data.get("tokens", [])}

        cleaned = []
        for e in usage_log:
            tid = e.get("token_id")
            token_data = token_map.get(tid) if tid else None
            eff_retention = None
            if token_data and token_data.get("stats_retention_days"):
                eff_retention = token_data["stats_retention_days"]
            elif retention_enabled:
                eff_retention = retention_days
            if eff_retention is not None:
                cutoff = now - (eff_retention * 86400)
                if e.get("timestamp", 0) < cutoff:
                    continue
            cleaned.append(e)

        if log_max_enabled and log_max > 0:
            cleaned = cleaned[:log_max]

        self.data["usage_log"] = cleaned

        # Move existing 401s to invalid_log
        invalid_log = self.data.setdefault("invalid_log", [])
        moved = [e for e in cleaned if e.get("status") == 401]
        kept = [e for e in cleaned if e.get("status") != 401]
        if moved:
            all_invalid = moved + invalid_log
            all_invalid.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            invalid_log = all_invalid[:log_max if log_max_enabled else len(all_invalid)]
            self.data["usage_log"] = kept

        cleaned_invalid = []
        invalid_retention = retention_days if retention_enabled else None
        for e in invalid_log:
            if invalid_retention is not None:
                cutoff = now - (invalid_retention * 86400)
                if e.get("timestamp", 0) < cutoff:
                    continue
            cleaned_invalid.append(e)
        if log_max_enabled and log_max > 0:
            cleaned_invalid = cleaned_invalid[:log_max]
        self.data["invalid_log"] = cleaned_invalid

try:
    from .api import async_setup_api
    HAS_API = True
except ImportError as err:
    _LOGGER.warning("API module not available: %s", err)
    HAS_API = False

async def _register_services(hass: HomeAssistant) -> None:
    def _mask_token(token: str) -> str:
        return token[:8] + "..." if len(token) > 8 else token

    async def _handle_list_tokens(call: ServiceCall) -> dict[str, Any]:
        handler: ReadOnlyDataHandler = hass.data[DOMAIN]["handler"]
        tokens = []
        for t in handler.data.get("tokens", []):
            tokens.append({
                "id": t["id"],
                "name": t.get("name", "Unnamed"),
                "token_masked": _mask_token(t.get("token_hash", "")),
                "created_at": t.get("created_at"),
                "expires_at": t.get("expires_at"),
                "domains": t.get("domains", []),
                "areas": t.get("areas", []),
                "allowed_ips": t.get("allowed_ips", []),
                "color": t.get("color", ""),
            })
        return {"tokens": tokens, "count": len(tokens)}

    async def _handle_get_token_info(call: ServiceCall) -> dict[str, Any]:
        handler: ReadOnlyDataHandler = hass.data[DOMAIN]["handler"]
        target_name = call.data["token_name"].lower()
        for t in handler.data.get("tokens", []):
            if t.get("name", "").lower() == target_name:
                return {
                    "found": True,
                    "id": t["id"],
                    "name": t.get("name", "Unnamed"),
                    "token_masked": _mask_token(t.get("token_hash", "")),
                    "created_at": t.get("created_at"),
                    "expires_at": t.get("expires_at"),
                    "domains": t.get("domains", []),
                    "patterns": t.get("patterns", ""),
                    "blocked_patterns": t.get("blocked_patterns", ""),
                    "areas": t.get("areas", []),
                    "allowed_entities": t.get("allowed_entities", []),
                    "allowed_ips": t.get("allowed_ips", []),
                    "include_attributes": t.get("include_attributes", True),
                    "color": t.get("color", ""),
                    "rate_limit_max_requests": t.get("rate_limit_max_requests"),
                    "rate_limit_window_value": t.get("rate_limit_window_value"),
                    "rate_limit_window_unit": t.get("rate_limit_window_unit"),
                    "stats_retention_days": t.get("stats_retention_days"),
                    "regeneration_count": t.get("regeneration_count", 0),
                }
        return {"found": False, "error": "Token not found"}

    hass.services.async_register(DOMAIN, SERVICE_LIST_TOKENS, _handle_list_tokens)
    hass.services.async_register(DOMAIN, SERVICE_GET_TOKEN_INFO, _handle_get_token_info, schema=SERVICE_GET_TOKEN_INFO_SCHEMA)
    _LOGGER.info("Services registered: %s, %s", SERVICE_LIST_TOKENS, SERVICE_GET_TOKEN_INFO)

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
            require_admin=True,
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
        
        _register_services(hass)
        
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