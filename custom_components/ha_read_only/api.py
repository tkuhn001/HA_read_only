from __future__ import annotations

import fnmatch

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import (
    API_PREFIX,
    CONF_ALLOWED_DOMAINS,
    CONF_ALLOWED_AREAS,
    CONF_ALLOWED_ENTITIES,
    CONF_ALLOWED_PATTERNS,
    CONF_BLOCKED_ENTITIES,
    CONF_BLOCKED_PATTERNS,
    CONF_INCLUDE_ATTRIBUTES,
    CONF_PROVIDE_ENTITIES_LIST,
    CONF_RETURN_ONLY_IDS,
    CONF_TOKEN,
    DOMAIN,
    HEADER_TOKEN_NAME,
)


async def async_setup_api(hass: HomeAssistant) -> None:
    """Register the API views."""
    hass.http.register_view(StatesView)
    hass.http.register_view(SingleStateView)
    hass.http.register_view(EntityListView)


def _find_entry_by_token(hass: HomeAssistant, token: str):
    """Find config entry matching the given token."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_TOKEN) == token:
            return entry
    return None


def _build_response(state_entry, include_attrs: bool) -> dict:
    """Build a state response dict."""
    result = {
        "entity_id": state_entry.entity_id,
        "state": state_entry.state,
    }
    if include_attrs:
        result["attributes"] = dict(state_entry.attributes)
    return result


def _match_patterns(entity_id: str, patterns: list[str]) -> bool:
    """Check if entity_id matches any of the fnmatch patterns."""
    for pattern in patterns:
        if fnmatch.fnmatch(entity_id, pattern):
            return True
    return False


def _get_area_entity_ids(hass: HomeAssistant, area_ids: set[str]) -> set[str]:
    """Resolve area IDs to entity IDs using the entity registry."""
    ent_reg = hass.helpers.entity_registry.async_get(hass)
    area_entities = set()
    for entity_entry in ent_reg.entities.values():
        if entity_entry.area_id in area_ids:
            area_entities.add(entity_entry.entity_id)
    return area_entities


def _is_entity_allowed(
    entity_id: str, data: dict, hass: HomeAssistant,
    area_entities_cache: set[str] | None = None,
) -> bool:
    """Check if a single entity is allowed based on token config."""
    allowed_domains = set(data.get(CONF_ALLOWED_DOMAINS, []))
    allowed_entities = set(data.get(CONF_ALLOWED_ENTITIES, []))
    allowed_patterns = [
        p.strip()
        for p in data.get(CONF_ALLOWED_PATTERNS, "").split("\n")
        if p.strip()
    ]
    allowed_areas = set(data.get(CONF_ALLOWED_AREAS, []))

    blocked_entities = set(data.get(CONF_BLOCKED_ENTITIES, []))
    blocked_patterns = [
        p.strip()
        for p in data.get(CONF_BLOCKED_PATTERNS, "").split("\n")
        if p.strip()
    ]

    domain = entity_id.split(".", 1)[0]

    no_allow_restrictions = (
        not allowed_domains
        and not allowed_entities
        and not allowed_patterns
        and not allowed_areas
    )

    allowed = False
    if no_allow_restrictions:
        allowed = True
    else:
        if domain in allowed_domains:
            allowed = True
        if entity_id in allowed_entities:
            allowed = True
        if allowed_areas:
            if area_entities_cache is None:
                area_entities_cache = _get_area_entity_ids(hass, allowed_areas)
            if entity_id in area_entities_cache:
                allowed = True
        if allowed_patterns and _match_patterns(entity_id, allowed_patterns):
            allowed = True

    if not allowed:
        return False

    if entity_id in blocked_entities:
        return False
    if blocked_patterns and _match_patterns(entity_id, blocked_patterns):
        return False

    return True


def _get_allowed_states(hass: HomeAssistant, data: dict) -> list[dict]:
    """Get filtered list of allowed states."""
    include_attrs = data.get(CONF_INCLUDE_ATTRIBUTES, True)
    allowed_areas = set(data.get(CONF_ALLOWED_AREAS, []))
    area_entities_cache = (
        _get_area_entity_ids(hass, allowed_areas) if allowed_areas else None
    )

    result = []
    for state in hass.states.async_all():
        if _is_entity_allowed(
            state.entity_id, data, hass, area_entities_cache,
        ):
            result.append(_build_response(state, include_attrs))

    return result


class StatesView(HomeAssistantView):
    """GET /api/ha_read_only/states – all allowed states."""

    url = f"{API_PREFIX}/states"
    name = f"{DOMAIN}:states"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)

        if not token:
            return web.json_response({"error": "Token required"}, status=401)

        entry = _find_entry_by_token(hass, token)
        if not entry:
            return web.json_response({"error": "Invalid token"}, status=401)

        try:
            states = _get_allowed_states(hass, entry.data)
            return web.json_response(states)
        except Exception as err:
            return web.json_response({"error": str(err)}, status=500)


class SingleStateView(HomeAssistantView):
    """GET /api/ha_read_only/states/<entity_id> – single state."""

    url = f"{API_PREFIX}/states/{{entity_id}}"
    name = f"{DOMAIN}:single_state"
    requires_auth = False

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)

        if not token:
            return web.json_response({"error": "Token required"}, status=401)

        entry = _find_entry_by_token(hass, token)
        if not entry:
            return web.json_response({"error": "Invalid token"}, status=401)

        if not _is_entity_allowed(entity_id, entry.data, hass):
            return web.json_response({"error": "Entity not allowed"}, status=403)

        state = hass.states.get(entity_id)
        if not state:
            return web.json_response({"error": "Entity not found"}, status=404)

        include_attrs = entry.data.get(CONF_INCLUDE_ATTRIBUTES, True)
        return web.json_response(_build_response(state, include_attrs))


class EntityListView(HomeAssistantView):
    """GET /api/ha_read_only/entities – list of allowed entities."""

    url = f"{API_PREFIX}/entities"
    name = f"{DOMAIN}:entities"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)

        if not token:
            return web.json_response({"error": "Token required"}, status=401)

        entry = _find_entry_by_token(hass, token)
        if not entry:
            return web.json_response({"error": "Invalid token"}, status=401)

        if not entry.data.get(CONF_PROVIDE_ENTITIES_LIST, False):
            return web.json_response(
                {"error": "Entity list endpoint is not enabled for this token"},
                status=403,
            )

        try:
            states = _get_allowed_states(hass, entry.data)
            only_ids = entry.data.get(CONF_RETURN_ONLY_IDS, False)
            if only_ids:
                return web.json_response([s["entity_id"] for s in states])
            return web.json_response(states)
        except Exception as err:
            return web.json_response({"error": str(err)}, status=500)
