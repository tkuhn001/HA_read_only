import secrets

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import CONF_TOKEN, DOMAIN
from .api import async_setup_api


SERVICE_REGENERATE_TOKEN = "regenerate_token"

SERVICE_REGENERATE_SCHEMA = vol.Schema({
    vol.Optional("old_token"): cv.string,
    vol.Optional("token_name"): cv.string,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HA Read-Only API from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    if "api_registered" not in hass.data[DOMAIN]:
        await async_setup_api(hass)
        hass.data[DOMAIN]["api_registered"] = True

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
            if token_name and entry.title == token_name:
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

    hass.services.async_register(
        DOMAIN,
        SERVICE_REGENERATE_TOKEN,
        handle_regenerate_token,
        schema=SERVICE_REGENERATE_SCHEMA,
    )


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update entry when options are updated."""
    hass.data[DOMAIN][entry.entry_id] = entry.data


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        del hass.data[DOMAIN][entry.entry_id]
    return True
