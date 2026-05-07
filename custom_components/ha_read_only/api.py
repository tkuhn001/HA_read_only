from __future__ import annotations

import fnmatch
import logging
import time

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

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
    RATE_LIMIT_MAX_PER_IP,
    RATE_LIMIT_MAX_PER_TOKEN,
    RATE_LIMIT_WINDOW,
)

_LOGGER = logging.getLogger(__name__)

_RATE_LIMITS: dict[tuple[str, str], list[float]] = {}

try:
    from homeassistant.helpers.http import HomeAssistantView
except ImportError:
    HomeAssistantView = None
    _LOGGER.warning(
        "HomeAssistantView not available; read-only API endpoints disabled."
    )


def _rate_limit(key: tuple[str, str]) -> bool:
    """Check and record a request for rate limiting. Returns True if allowed."""
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW
    records = _RATE_LIMITS.get(key, [])
    records = [t for t in records if t > window_start]
    max_limit = RATE_LIMIT_MAX_PER_IP if key[0] == "ip" else RATE_LIMIT_MAX_PER_TOKEN
    if len(records) >= max_limit:
        return False
    records.append(now)
    _RATE_LIMITS[key] = records
    if len(_RATE_LIMITS) > 10000:
        _trim_rate_limits()
    return True


def _trim_rate_limits() -> None:
    """Remove expired entries from rate limit cache."""
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW
    expired = [k for k, v in _RATE_LIMITS.items() if not any(t > cutoff for t in v)]
    for k in expired:
        del _RATE_LIMITS[k]


async def async_setup_api(hass: HomeAssistant) -> None:
    """Register the API views."""
    if HomeAssistantView is None:
        _LOGGER.warning("Cannot register API views – HomeAssistantView not available")
        return
    hass.http.register_view(StatesView)
    hass.http.register_view(SingleStateView)
    hass.http.register_view(EntityListView)
    _LOGGER.info("Read-only API endpoints registered at %s/*", API_PREFIX)


def _get_client_ip(request: web.Request) -> str:
    """Extract client IP from request."""
    if forwarded := request.headers.get("X-Forwarded-For"):
        return forwarded.split(",")[0].strip()
    if peername := request.transport.get_extra_info("peername"):
        return peername[0]
    return "unknown"


def _get_token_name(hass: HomeAssistant, token: str) -> str:
    """Get the friendly name for a token."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_TOKEN) == token:
            return entry.title or entry.data.get(CONF_TOKEN_NAME, "Unnamed")
    return "Unknown"


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
    ent_reg = async_get_entity_registry(hass)
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


if HomeAssistantView is not None:

    class StatesView(HomeAssistantView):
        """GET /api/ha_read_only/states – all allowed states."""

        url = f"{API_PREFIX}/states"
        name = f"{DOMAIN}:states"
        requires_auth = False

        async def get(self, request: web.Request) -> web.Response:
            hass = request.app["hass"]
            ip = _get_client_ip(request)
            token = request.headers.get(HEADER_TOKEN_NAME)

            if not _rate_limit(("ip", ip)):
                _LOGGER.warning("Rate limit exceeded for IP %s", ip)
                return web.json_response({"error": "Too many requests"}, status=429)
            if token and not _rate_limit(("token", token)):
                _LOGGER.warning("Rate limit exceeded for token")
                return web.json_response({"error": "Too many requests"}, status=429)

            if not token:
                _LOGGER.warning("Request without token from IP %s", ip)
                return web.json_response({"error": "Token required"}, status=401)

            entry = _find_entry_by_token(hass, token)
            if not entry:
                _LOGGER.warning("Invalid token attempt from IP %s", ip)
                return web.json_response({"error": "Invalid token"}, status=401)

            try:
                states = _get_allowed_states(hass, entry.data)
                token_name = _get_token_name(hass, token)
                _LOGGER.info(
                    "States request – token: %s, entities: %d",
                    token_name, len(states),
                )
                return web.json_response(states)
            except Exception as err:
                _LOGGER.exception("Error processing states request: %s", err)
                return web.json_response({"error": str(err)}, status=500)

    class SingleStateView(HomeAssistantView):
        """GET /api/ha_read_only/states/<entity_id> – single state."""

        url = f"{API_PREFIX}/states/{{entity_id}}"
        name = f"{DOMAIN}:single_state"
        requires_auth = False

        async def get(self, request: web.Request, entity_id: str) -> web.Response:
            hass = request.app["hass"]
            ip = _get_client_ip(request)
            token = request.headers.get(HEADER_TOKEN_NAME)

            if not _rate_limit(("ip", ip)):
                _LOGGER.warning("Rate limit exceeded for IP %s", ip)
                return web.json_response({"error": "Too many requests"}, status=429)
            if token and not _rate_limit(("token", token)):
                _LOGGER.warning("Rate limit exceeded for token")
                return web.json_response({"error": "Too many requests"}, status=429)

            if not token:
                _LOGGER.warning("Request without token from IP %s", ip)
                return web.json_response({"error": "Token required"}, status=401)

            entry = _find_entry_by_token(hass, token)
            if not entry:
                _LOGGER.warning("Invalid token attempt from IP %s", ip)
                return web.json_response({"error": "Invalid token"}, status=401)

            if not _is_entity_allowed(entity_id, entry.data, hass):
                token_name = _get_token_name(hass, token)
                _LOGGER.info(
                    "Blocked entity %s for token %s", entity_id, token_name,
                )
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
            ip = _get_client_ip(request)
            token = request.headers.get(HEADER_TOKEN_NAME)

            if not _rate_limit(("ip", ip)):
                _LOGGER.warning("Rate limit exceeded for IP %s", ip)
                return web.json_response({"error": "Too many requests"}, status=429)
            if token and not _rate_limit(("token", token)):
                _LOGGER.warning("Rate limit exceeded for token")
                return web.json_response({"error": "Too many requests"}, status=429)

            if not token:
                _LOGGER.warning("Request without token from IP %s", ip)
                return web.json_response({"error": "Token required"}, status=401)

            entry = _find_entry_by_token(hass, token)
            if not entry:
                _LOGGER.warning("Invalid token attempt from IP %s", ip)
                return web.json_response({"error": "Invalid token"}, status=401)

            if not entry.data.get(CONF_PROVIDE_ENTITIES_LIST, False):
                return web.json_response(
                    {"error": "Entity list endpoint is not enabled for this token"},
                    status=403,
                )

            try:
                states = _get_allowed_states(hass, entry.data)
                only_ids = entry.data.get(CONF_RETURN_ONLY_IDS, False)
                token_name = _get_token_name(hass, token)
                _LOGGER.info(
                    "Entity list request – token: %s, entities: %d",
                    token_name, len(states),
                )
                if only_ids:
                    return web.json_response([s["entity_id"] for s in states])
                return web.json_response(states)
            except Exception as err:
                _LOGGER.exception("Error processing entities request: %s", err)
                return web.json_response({"error": str(err)}, status=500)
