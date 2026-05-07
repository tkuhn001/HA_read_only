import logging
import secrets

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import CONF_TOKEN, CONF_TOKEN_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

try:
    from .api import async_setup_api

    HAS_API = True
except ImportError as err:
    _LOGGER.warning("API module not available, read-only HTTP endpoints disabled: %s", err)
    HAS_API = False


SERVICE_REGENERATE_TOKEN = "regenerate_token"
SERVICE_LIST_TOKENS = "list_tokens"
SERVICE_GET_TOKEN_INFO = "get_token_info"
SERVICE_DELETE_TOKEN = "delete_token"

SERVICE_REGENERATE_SCHEMA = vol.Schema({
    vol.Optional("old_token"): cv.string,
    vol.Optional("token_name"): cv.string,
})

SERVICE_LIST_TOKENS_SCHEMA = vol.Schema({})

SERVICE_GET_TOKEN_INFO_SCHEMA = vol.Schema({
    vol.Required("token_name"): cv.string,
})

SERVICE_DELETE_TOKEN_SCHEMA = vol.Schema({
    vol.Required("token_name"): cv.string,
})


def _mask_token(token: str) -> str:
    """Mask a token for display, showing first 8 chars."""
    if len(token) <= 8:
        return token
    return token[:8] + "…"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Read-Only API from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    if HAS_API and "api_registered" not in hass.data[DOMAIN]:
        try:
            await async_setup_api(hass)
            hass.data[DOMAIN]["api_registered"] = True
        except Exception as err:
            _LOGGER.exception("Failed to set up API: %s", err)

    if "services_registered" not in hass.data[DOMAIN]:
        await async_setup_services(hass)
        hass.data[DOMAIN]["services_registered"] = True

    entry.async_on_unload(entry.add_update_listener(async_update_entry))

    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register services."""

    async def handle_regenerate_token(call: ServiceCall) -> None:
        old_token = call.data.get("old_token")
        token_name = call.data.get("token_name")

        target_entry = None
        for entry in hass.config_entries.async_entries(DOMAIN):
            if old_token and entry.data.get(CONF_TOKEN) == old_token:
                target_entry = entry
                break
            if token_name and (entry.title == token_name or entry.data.get(CONF_TOKEN_NAME) == token_name):
                target_entry = entry
                break

        if not target_entry:
            raise ValueError(
                "Kein Eintrag mit dem angegebenen Token oder Namen gefunden."
            )

        new_data = dict(target_entry.data)
        new_data[CONF_TOKEN] = secrets.token_urlsafe(32)
        hass.config_entries.async_update_entry(target_entry, data=new_data)
        hass.data[DOMAIN][target_entry.entry_id] = new_data
        _LOGGER.info("Token regenerated for entry '%s'", target_entry.title)

    async def handle_list_tokens(call: ServiceCall) -> list[dict]:
        entries = [
            {
                "name": e.title,
                "token_masked": _mask_token(e.data.get(CONF_TOKEN, "")),
                "entry_id": e.entry_id,
            }
            for e in hass.config_entries.async_entries(DOMAIN)
        ]
        _LOGGER.info("Token list requested – %d tokens found", len(entries))
        return entries

    async def handle_get_token_info(call: ServiceCall) -> dict | None:
        token_name = call.data["token_name"]
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.title == token_name or entry.data.get(CONF_TOKEN_NAME) == token_name:
                data = dict(entry.data)
                data[CONF_TOKEN] = _mask_token(data.get(CONF_TOKEN, ""))
                data["entry_id"] = entry.entry_id
                return data
        raise ValueError(f"Kein Eintrag mit dem Namen '{token_name}' gefunden.")

    async def handle_delete_token(call: ServiceCall) -> None:
        token_name = call.data["token_name"]
        target_entry = None
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.title == token_name or entry.data.get(CONF_TOKEN_NAME) == token_name:
                target_entry = entry
                break
        if not target_entry:
            raise ValueError(f"Kein Eintrag mit dem Namen '{token_name}' gefunden.")
        entry_id = target_entry.entry_id
        await hass.config_entries.async_remove(entry_id)
        hass.data.get(DOMAIN, {}).pop(entry_id, None)
        _LOGGER.info("Token entry '%s' deleted", token_name)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REGENERATE_TOKEN,
        handle_regenerate_token,
        schema=SERVICE_REGENERATE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LIST_TOKENS,
        handle_list_tokens,
        schema=SERVICE_LIST_TOKENS_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_TOKEN_INFO,
        handle_get_token_info,
        schema=SERVICE_GET_TOKEN_INFO_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_TOKEN,
        handle_delete_token,
        schema=SERVICE_DELETE_TOKEN_SCHEMA,
    )


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update entry when options are updated."""
    hass.data[DOMAIN][entry.entry_id] = entry.data


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        del hass.data[DOMAIN][entry.entry_id]
    return True
