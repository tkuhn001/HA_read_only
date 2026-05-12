from __future__ import annotations

import fnmatch
import logging
import os
import secrets
import time
from typing import Any

from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import HomeAssistantView

from .const import (
    API_PREFIX,
    CONF_TOKEN,
    DOMAIN,
    HEADER_TOKEN_NAME,
    RATE_LIMIT_MAX_PER_IP,
    RATE_LIMIT_MAX_PER_TOKEN,
    RATE_LIMIT_WINDOW,
)

_LOGGER = logging.getLogger(__name__)
_RATE_LIMIT_CACHE: dict[tuple[str, str], list[float]] = {}

# Load HTML from file (avoids string escaping issues)
_HTML_PATH = os.path.join(os.path.dirname(__file__), "admin.html")
try:
    with open(_HTML_PATH, "r", encoding="utf-8") as f:
        ADMIN_HTML = f.read()
except Exception:
    ADMIN_HTML = "<html><body><h1>Error: admin.html not found</h1></body></html>"


def _get_handler(hass: HomeAssistant) -> Any:
    return hass.data[DOMAIN]["handler"]


def _rate_limit(hass: HomeAssistant, key: tuple[str, str]) -> bool:
    now = time.monotonic()
    handler = _get_handler(hass)
    config = handler.data.get("config", {})
    window = config.get("rate_limit_window", RATE_LIMIT_WINDOW)
    max_limit = (
        config.get("rate_limit_max_per_ip", RATE_LIMIT_MAX_PER_IP)
        if key[0] == "ip"
        else config.get("rate_limit_max_per_token", RATE_LIMIT_MAX_PER_TOKEN)
    )
    records = _RATE_LIMIT_CACHE.get(key, [])
    records = [t for t in records if t > now - window]
    if len(records) >= max_limit:
        return False
    records.append(now)
    _RATE_LIMIT_CACHE[key] = records
    return True


async def _track_usage(
    hass: HomeAssistant, token: str, endpoint: str, status: int, token_name: str = ""
) -> None:
    handler = _get_handler(hass)
    stats = handler.data.setdefault("stats", {})
    key = token or "no_token"
    entry = stats.setdefault(
        key,
        {
            "token_name": token_name,
            "total": 0,
            "by_endpoint": {},
            "errors": 0,
            "last_access": None,
            "last_endpoint": None,
        },
    )
    entry["total"] += 1
    entry["by_endpoint"][endpoint] = entry["by_endpoint"].get(endpoint, 0) + 1
    if status >= 400:
        entry["errors"] += 1
    entry["last_access"] = time.time()
    entry["last_endpoint"] = endpoint
    if token_name:
        entry["token_name"] = token_name
    await handler.async_save()


def _mask_token(token: str) -> str:
    return token[:8] + "..." if len(token) > 8 else token


def _get_client_ip(request: web.Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    peer = request.transport.get_extra_info("peername")
    return peer[0] if peer else "unknown"


def _find_token_data(hass: HomeAssistant, token: str) -> dict | None:
    for t in _get_handler(hass).data.get("tokens", []):
        if t.get(CONF_TOKEN) == token:
            return t
    return None


def _to_pattern_list(value) -> list[str]:
    """Convert patterns from string or list to a list of stripped strings."""
    if isinstance(value, list):
        return [p.strip() for p in value if isinstance(p, str) and p.strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split("\n") if p.strip()]
    return []


def _is_entity_allowed(entity_id: str, token_data: dict, hass: HomeAssistant) -> bool:
    allowed_domains = set(token_data.get("domains", []))
    allowed_patterns = _to_pattern_list(token_data.get("patterns", ""))
    blocked_patterns = _to_pattern_list(token_data.get("blocked_patterns", ""))
    domain = entity_id.split(".", 1)[0]

    # Blocklist is absolute
    for pat in blocked_patterns:
        if fnmatch.fnmatch(entity_id, pat):
            return False

    # If nothing specified, allow all
    if not allowed_domains and not allowed_patterns:
        return True

    if domain in allowed_domains:
        return True
    for pat in allowed_patterns:
        if fnmatch.fnmatch(entity_id, pat):
            return True
    return False


def _build_response(state, include_attrs: bool) -> dict:
    res = {"entity_id": state.entity_id, "state": state.state}
    if include_attrs:
        res["attributes"] = dict(state.attributes)
    return res


# --- API SETUP ---

async def async_setup_api(hass: HomeAssistant) -> None:
    hass.http.register_view(AdminPanelView)
    hass.http.register_view(AdminApiOptionsView)
    hass.http.register_view(AdminApiTokensView)
    hass.http.register_view(AdminApiTokenView)
    hass.http.register_view(AdminApiTokenRegenerateView)
    hass.http.register_view(AdminApiStatsView)
    hass.http.register_view(AdminApiConfigView)
    hass.http.register_view(StatesView)
    hass.http.register_view(SingleStateView)
    hass.http.register_view(EntityListView)


# --- ADMIN VIEWS ---

class AdminPanelView(HomeAssistantView):
    url = f"{API_PREFIX}/admin"
    name = f"{DOMAIN}:admin_panel"
    requires_auth = False

    async def get(self, request):
        return web.Response(text=ADMIN_HTML, content_type="text/html")


class AdminApiOptionsView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/options"
    name = f"{DOMAIN}:admin_api_options"
    requires_auth = False

    async def get(self, request):
        hass = request.app["hass"]
        domains = sorted(set(s.domain for s in hass.states.async_all()))
        return web.json_response({"domains": domains})


class AdminApiTokensView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens"
    name = f"{DOMAIN}:admin_api_tokens"
    requires_auth = False

    async def get(self, request):
        handler = _get_handler(request.app["hass"])
        result = []
        for t in handler.data.get("tokens", []):
            result.append({**t, "token_masked": _mask_token(t.get(CONF_TOKEN, ""))})
        return web.json_response(result)

    async def post(self, request):
        data = await request.json()
        token = secrets.token_urlsafe(32)
        new_token = {
            "id": secrets.token_hex(4),
            "name": data.get("name", "Unnamed"),
            CONF_TOKEN: token,
            "domains": data.get("domains", []),
            "patterns": data.get("patterns", ""),
            "blocked_patterns": data.get("blocked_patterns", ""),
            "include_attributes": data.get("include_attributes", True),
            "created_at": time.time(),
        }
        handler = _get_handler(request.app["hass"])
        handler.data.setdefault("tokens", []).append(new_token)
        await handler.async_save()
        return web.json_response({"token": token, "id": new_token["id"]}, status=201)


class AdminApiTokenView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}"
    name = f"{DOMAIN}:admin_api_token"
    requires_auth = False

    async def put(self, request, token_id):
        data = await request.json()
        handler = _get_handler(request.app["hass"])
        for t in handler.data.get("tokens", []):
            if t["id"] == token_id:
                t["name"] = data.get("name", t["name"])
                t["domains"] = data.get("domains", t.get("domains", []))
                t["patterns"] = data.get("patterns", t.get("patterns", ""))
                t["blocked_patterns"] = data.get("blocked_patterns", t.get("blocked_patterns", ""))
                t["include_attributes"] = data.get("include_attributes", t.get("include_attributes", True))
                break
        await handler.async_save()
        return web.json_response({"success": True})

    async def delete(self, request, token_id):
        handler = _get_handler(request.app["hass"])
        handler.data["tokens"] = [
            t for t in handler.data.get("tokens", []) if t["id"] != token_id
        ]
        await handler.async_save()
        return web.json_response({"success": True})


class AdminApiTokenRegenerateView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}/regenerate"
    name = f"{DOMAIN}:admin_api_token_regenerate"
    requires_auth = False

    async def post(self, request, token_id):
        handler = _get_handler(request.app["hass"])
        new_token = secrets.token_urlsafe(32)
        for t in handler.data.get("tokens", []):
            if t["id"] == token_id:
                t[CONF_TOKEN] = new_token
                break
        await handler.async_save()
        return web.json_response({"token": new_token})


class AdminApiStatsView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/stats"
    name = f"{DOMAIN}:admin_api_stats"
    requires_auth = False

    async def get(self, request):
        handler = _get_handler(request.app["hass"])
        stats = handler.data.get("stats", {})
        total_requests = sum(s["total"] for s in stats.values())
        total_errors = sum(s["errors"] for s in stats.values())
        tokens_stats = []
        for k, v in stats.items():
            tokens_stats.append({**v, "token_key": k[:8] + "..."})
        return web.json_response({
            "total_requests": total_requests,
            "total_errors": total_errors,
            "tokens": tokens_stats,
        })


class AdminApiConfigView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/config"
    name = f"{DOMAIN}:admin_api_config"
    requires_auth = False

    async def get(self, request):
        handler = _get_handler(request.app["hass"])
        return web.json_response(handler.data.get("config", {}))

    async def put(self, request):
        data = await request.json()
        handler = _get_handler(request.app["hass"])
        handler.data.setdefault("config", {}).update(data)
        await handler.async_save()
        return web.json_response({"success": True})


# --- PUBLIC API ENDPOINTS ---

class StatesView(HomeAssistantView):
    url = f"{API_PREFIX}/states"
    name = f"{DOMAIN}:states"
    requires_auth = False

    async def get(self, request):
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)
        ip = _get_client_ip(request)

        if not _rate_limit(hass, ("ip", ip)):
            return web.json_response({"error": "Too many requests"}, status=429)
        if token and not _rate_limit(hass, ("token", token)):
            return web.json_response({"error": "Too many requests"}, status=429)

        token_data = _find_token_data(hass, token)
        if not token_data:
            await _track_usage(hass, token, "GET /states", 401)
            return web.json_response({"error": "Invalid token"}, status=401)

        incl_attrs = token_data.get("include_attributes", True)
        states = []
        for state in hass.states.async_all():
            if _is_entity_allowed(state.entity_id, token_data, hass):
                states.append(_build_response(state, incl_attrs))

        await _track_usage(hass, token, "GET /states", 200, token_data.get("name"))
        return web.json_response(states)


class SingleStateView(HomeAssistantView):
    url = f"{API_PREFIX}/states/{{entity_id}}"
    name = f"{DOMAIN}:single_state"
    requires_auth = False

    async def get(self, request, entity_id):
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)
        token_data = _find_token_data(hass, token)
        if not token_data or not _is_entity_allowed(entity_id, token_data, hass):
            return web.json_response({"error": "Unauthorized"}, status=401)

        state = hass.states.get(entity_id)
        if not state:
            return web.json_response({"error": "Not found"}, status=404)

        incl_attrs = token_data.get("include_attributes", True)
        await _track_usage(hass, token, f"GET /states/{entity_id}", 200, token_data.get("name"))
        return web.json_response(_build_response(state, incl_attrs))


class EntityListView(HomeAssistantView):
    url = f"{API_PREFIX}/entities"
    name = f"{DOMAIN}:entities"
    requires_auth = False

    async def get(self, request):
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)
        token_data = _find_token_data(hass, token)
        if not token_data:
            return web.json_response({"error": "Unauthorized"}, status=401)

        entities = [
            s.entity_id
            for s in hass.states.async_all()
            if _is_entity_allowed(s.entity_id, token_data, hass)
        ]
        await _track_usage(hass, token, "GET /entities", 200, token_data.get("name"))
        return web.json_response(entities)
