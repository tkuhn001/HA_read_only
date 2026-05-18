# HA Read-Only API – Home Assistant Integration
# Copyright (c) 2026 T. Kuhn
# Lizenz: MIT – Siehe LICENSE-Datei im Repository
#
# DIE SOFTWARE WIRD "AS IS" BEREITGESTELLT, OHNE JEGLICHE GEWÄHRLEISTUNG.
# NUTZUNG AUF EIGENE GEFAHR.

from __future__ import annotations

import fnmatch
import ipaddress
import logging
import os
import secrets
import time
from datetime import datetime
from typing import Any

import aiohttp
from aiohttp import web
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.http import HomeAssistantView

from .const import (
    API_PREFIX,
    CONF_TOKEN,
    CONF_WEBHOOK_ON_API,
    CONF_WEBHOOK_ON_TOKEN,
    CONF_WEBHOOK_URL,
    DOMAIN,
    HEADER_TOKEN_NAME,
    RATE_LIMIT_MAX_PER_IP,
    RATE_LIMIT_MAX_PER_TOKEN,
    RATE_LIMIT_WINDOW,
    USAGE_LOG_MAX,
    VERSION,
)

API_HELP = {
    "name": "HA Read-Only API",
    "version": VERSION,
    "read_only": True,
    "auth": {
        "header": HEADER_TOKEN_NAME,
        "description": "Token aus dem Dashboard unter „Tokens“",
    },
    "endpoints": [
        {
            "method": "GET",
            "path": f"{API_PREFIX}/help",
            "description": "Kurzübersicht aller API-Endpunkte (dieser Endpunkt)",
            "auth_required": False,
        },
        {
            "method": "GET",
            "path": f"{API_PREFIX}/states",
            "description": "Alle erlaubten Entity-Zustände (state + optional attributes)",
            "auth_required": True,
        },
        {
            "method": "GET",
            "path": f"{API_PREFIX}/states/{{entity_id}}",
            "description": "Zustand einer einzelnen Entität",
            "auth_required": True,
        },
        {
            "method": "GET",
            "path": f"{API_PREFIX}/entities",
            "description": "Liste der erlaubten Entity-IDs (ohne Zustände)",
            "auth_required": True,
        },
    ],
}

_LOGGER = logging.getLogger(__name__)

_HTML_PATH = os.path.join(os.path.dirname(__file__), "admin.html")
try:
    with open(_HTML_PATH, "r", encoding="utf-8") as f:
        ADMIN_HTML = f.read()
except Exception:
    ADMIN_HTML = "<html><body><h1>Error: admin.html not found</h1></body></html>"


def _get_handler(hass: HomeAssistant) -> Any:
    return hass.data[DOMAIN]["handler"]


def _rate_limit_key(key: tuple[str, str]) -> str:
    return f"{key[0]}|{key[1]}"


def _rate_limit(hass: HomeAssistant, key: tuple[str, str]) -> bool:
    now = time.time()
    handler = _get_handler(hass)
    config = handler.data.get("config", {})
    window = config.get("rate_limit_window", RATE_LIMIT_WINDOW)
    max_limit = (
        config.get("rate_limit_max_per_ip", RATE_LIMIT_MAX_PER_IP)
        if key[0] == "ip"
        else config.get("rate_limit_max_per_token", RATE_LIMIT_MAX_PER_TOKEN)
    )
    cache = handler.data.setdefault("rate_limit", {})
    cache_key = _rate_limit_key(key)
    records = [t for t in cache.get(cache_key, []) if t > now - window]
    if len(records) >= max_limit:
        return False
    records.append(now)
    cache[cache_key] = records
    return True


def _compute_hourly_chart(usage_log: list[dict]) -> list[int]:
    """Request counts per hour for the last 24 hours."""
    now = time.time()
    buckets = [0] * 24
    for entry in usage_log:
        ts = entry.get("timestamp")
        if not ts:
            continue
        age_hours = int((now - ts) // 3600)
        if 0 <= age_hours < 24:
            buckets[23 - age_hours] += 1
    return buckets


async def _fire_webhook(hass: HomeAssistant, event: str, payload: dict) -> None:
    config = _get_handler(hass).data.get("config", {})
    url = config.get(CONF_WEBHOOK_URL, "").strip()
    if not url:
        return
    if event == "api_request" and not config.get(CONF_WEBHOOK_ON_API):
        return
    if event == "token_created" and not config.get(CONF_WEBHOOK_ON_TOKEN):
        return
    body = {"event": event, "timestamp": time.time(), **payload}
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, timeout=timeout) as resp:
                if resp.status >= 400:
                    _LOGGER.warning("Webhook returned %s", resp.status)
    except Exception as err:
        _LOGGER.warning("Webhook failed: %s", err)


async def _track_usage(
    hass: HomeAssistant,
    token: str | None,
    endpoint: str,
    status: int,
    token_name: str = "",
    ip: str = "",
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

    log_entry = {
        "timestamp": time.time(),
        "ip": ip or "unknown",
        "endpoint": endpoint,
        "status": status,
        "token_name": token_name or (key[:8] + "..." if key != "no_token" else "—"),
    }
    usage_log = handler.data.setdefault("usage_log", [])
    usage_log.insert(0, log_entry)
    handler.data["usage_log"] = usage_log[:USAGE_LOG_MAX]

    await handler.async_save()

    if status == 200 and token:
        await _fire_webhook(
            hass,
            "api_request",
            {
                "endpoint": endpoint,
                "token_name": token_name,
                "ip": ip,
            },
        )


def _mask_token(token: str) -> str:
    return token[:8] + "..." if len(token) > 8 else token


def _get_client_ip(request: web.Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    peer = request.transport.get_extra_info("peername")
    return peer[0] if peer else "unknown"


def _find_token_data(hass: HomeAssistant, token: str | None) -> dict | None:
    if not token:
        return None
    for t in _get_handler(hass).data.get("tokens", []):
        if t.get(CONF_TOKEN) == token:
            return t
    return None


def _to_pattern_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [p.strip() for p in value if isinstance(p, str) and p.strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split("\n") if p.strip()]
    return []


def _parse_ip_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [
            x.strip()
            for x in value.replace(",", "\n").split("\n")
            if x.strip()
        ]
    return []


def _parse_expires_at(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _is_token_valid(token_data: dict) -> bool:
    expires_at = token_data.get("expires_at")
    if expires_at is None:
        return True
    return time.time() < float(expires_at)


def _ip_matches(client_ip: str, allowed: str) -> bool:
    try:
        if "/" in allowed:
            network = ipaddress.ip_network(allowed, strict=False)
            return ipaddress.ip_address(client_ip) in network
        return client_ip == allowed
    except ValueError:
        return False


def _is_ip_allowed(client_ip: str, allowed_ips: list[str]) -> bool:
    if not allowed_ips:
        return True
    return any(_ip_matches(client_ip, entry) for entry in allowed_ips)


def _get_entity_area(hass: HomeAssistant, entity_id: str) -> str | None:
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None:
        return None
    return entry.area_id


def _is_entity_allowed(entity_id: str, token_data: dict, hass: HomeAssistant) -> bool:
    allowed_domains = set(token_data.get("domains", []))
    allowed_patterns = _to_pattern_list(token_data.get("patterns", ""))
    blocked_patterns = _to_pattern_list(token_data.get("blocked_patterns", ""))
    allowed_areas = set(token_data.get("areas", []))
    allowed_entities = set(token_data.get("allowed_entities", []))

    for pat in blocked_patterns:
        if fnmatch.fnmatch(entity_id, pat):
            return False

    has_whitelist = (
        bool(allowed_domains)
        or bool(allowed_patterns)
        or bool(allowed_areas)
        or bool(allowed_entities)
    )
    if not has_whitelist:
        return True

    if entity_id in allowed_entities:
        return True

    domain = entity_id.split(".", 1)[0]
    if domain in allowed_domains:
        return True

    for pat in allowed_patterns:
        if fnmatch.fnmatch(entity_id, pat):
            return True

    if allowed_areas:
        area_id = _get_entity_area(hass, entity_id)
        if area_id and area_id in allowed_areas:
            return True

    return False


def _build_response(state: Any, include_attrs: bool) -> dict:
    res = {"entity_id": state.entity_id, "state": state.state}
    if include_attrs:
        res["attributes"] = dict(state.attributes)
    return res


def _token_fields_from_request(data: dict) -> dict:
    return {
        "name": data.get("name", "Unnamed"),
        "domains": data.get("domains", []),
        "patterns": data.get("patterns", ""),
        "blocked_patterns": data.get("blocked_patterns", ""),
        "include_attributes": data.get("include_attributes", True),
        "expires_at": _parse_expires_at(data.get("expires_at")),
        "areas": data.get("areas", []),
        "allowed_ips": _parse_ip_list(data.get("allowed_ips", "")),
        "allowed_entities": data.get("allowed_entities", []),
    }


async def _validate_token_request(
    hass: HomeAssistant,
    request: web.Request,
    token: str | None,
    endpoint: str,
) -> tuple[dict | None, web.Response | None]:
    ip = _get_client_ip(request)

    if not _rate_limit(hass, ("ip", ip)):
        return None, web.json_response({"error": "Too many requests"}, status=429)

    if not token:
        await _track_usage(hass, None, endpoint, 401, ip=ip)
        return None, web.json_response({"error": "Invalid token"}, status=401)

    if not _rate_limit(hass, ("token", token)):
        return None, web.json_response({"error": "Too many requests"}, status=429)

    token_data = _find_token_data(hass, token)
    if not token_data:
        await _track_usage(hass, token, endpoint, 401, ip=ip)
        return None, web.json_response({"error": "Invalid token"}, status=401)

    if not _is_token_valid(token_data):
        await _track_usage(
            hass, token, endpoint, 401, token_data.get("name", ""), ip=ip
        )
        return None, web.json_response({"error": "Token expired"}, status=401)

    if not _is_ip_allowed(ip, token_data.get("allowed_ips", [])):
        await _track_usage(
            hass, token, endpoint, 403, token_data.get("name", ""), ip=ip
        )
        return None, web.json_response({"error": "IP not allowed"}, status=403)

    return token_data, None


# --- API SETUP ---


async def async_setup_api(hass: HomeAssistant) -> None:
    hass.http.register_view(AdminPanelView)
    hass.http.register_view(AdminApiOptionsView)
    hass.http.register_view(AdminApiEntitiesView)
    hass.http.register_view(AdminApiTokensView)
    hass.http.register_view(AdminApiTokenView)
    hass.http.register_view(AdminApiTokenRegenerateView)
    hass.http.register_view(AdminApiStatsView)
    hass.http.register_view(AdminApiConfigView)
    hass.http.register_view(HelpView)
    hass.http.register_view(StatesView)
    hass.http.register_view(SingleStateView)
    hass.http.register_view(EntityListView)


# --- ADMIN VIEWS ---


class AdminPanelView(HomeAssistantView):
    url = f"{API_PREFIX}/admin"
    name = f"{DOMAIN}:admin_panel"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        return web.Response(text=ADMIN_HTML, content_type="text/html")


class AdminApiOptionsView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/options"
    name = f"{DOMAIN}:admin_api_options"
    requires_auth = True


class AdminApiEntitiesView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/entities"
    name = f"{DOMAIN}:admin_api_entities"
    requires_auth = True


class AdminApiTokensView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens"
    name = f"{DOMAIN}:admin_api_tokens"
    requires_auth = True


class AdminApiTokenView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}"
    name = f"{DOMAIN}:admin_api_token"
    requires_auth = True


class AdminApiTokenRegenerateView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}/regenerate"
    name = f"{DOMAIN}:admin_api_token_regenerate"
    requires_auth = True


class AdminApiStatsView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/stats"
    name = f"{DOMAIN}:admin_api_stats"
    requires_auth = True


class AdminApiConfigView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/config"
    name = f"{DOMAIN}:admin_api_config"
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        return web.Response(text=ADMIN_HTML, content_type="text/html")


class AdminApiOptionsView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/options"
    name = f"{DOMAIN}:admin_api_options"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            domains = sorted({s.domain for s in hass.states.async_all()})
            area_reg = ar.async_get(hass)
            areas = [
                {"id": area.id, "name": area.name or area.id}
                for area in sorted(area_reg.areas.values(), key=lambda a: a.name or "")
            ]
            return web.json_response({"domains": domains, "areas": areas})
        except Exception as err:
            _LOGGER.error("Failed to load admin options: %s", err, exc_info=True)
            return web.json_response({"domains": [], "areas": [], "error": str(err)})


class AdminApiEntitiesView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/entities"
    name = f"{DOMAIN}:admin_api_entities"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        query = request.query.get("q", "").lower()
        entities = sorted(s.entity_id for s in hass.states.async_all())
        if query:
            entities = [e for e in entities if query in e]
        return web.json_response(entities[:150])


class AdminApiTokensView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens"
    name = f"{DOMAIN}:admin_api_tokens"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        handler = _get_handler(request.app["hass"])
        result = []
        for t in handler.data.get("tokens", []):
            result.append({**t, "token_masked": _mask_token(t.get(CONF_TOKEN, ""))})
        return web.json_response(result)

    async def post(self, request: web.Request) -> web.Response:
        data = await request.json()
        token = secrets.token_urlsafe(32)
        new_token = {
            "id": secrets.token_hex(4),
            CONF_TOKEN: token,
            "created_at": time.time(),
            **_token_fields_from_request(data),
        }
        handler = _get_handler(request.app["hass"])
        handler.data.setdefault("tokens", []).append(new_token)
        await handler.async_save()
        await _fire_webhook(
            request.app["hass"],
            "token_created",
            {"token_name": new_token["name"], "token_id": new_token["id"]},
        )
        return web.json_response({"token": token, "id": new_token["id"]}, status=201)


class AdminApiTokenView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}"
    name = f"{DOMAIN}:admin_api_token"
    requires_auth = False

    async def put(self, request: web.Request, token_id: str) -> web.Response:
        data = await request.json()
        handler = _get_handler(request.app["hass"])
        fields = _token_fields_from_request(data)
        for t in handler.data.get("tokens", []):
            if t["id"] == token_id:
                t.update(fields)
                break
        await handler.async_save()
        return web.json_response({"success": True})

    async def delete(self, request: web.Request, token_id: str) -> web.Response:
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

    async def post(self, request: web.Request, token_id: str) -> web.Response:
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

    async def get(self, request: web.Request) -> web.Response:
        handler = _get_handler(request.app["hass"])
        stats = handler.data.get("stats", {})
        usage_log = handler.data.get("usage_log", [])
        total_requests = sum(s["total"] for s in stats.values())
        total_errors = sum(s["errors"] for s in stats.values())
        tokens_stats = [{**v, "token_key": k[:8] + "..."} for k, v in stats.items()]
        return web.json_response(
            {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "tokens": tokens_stats,
                "usage_log": usage_log,
                "hourly": _compute_hourly_chart(usage_log),
            }
        )


class AdminApiConfigView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/config"
    name = f"{DOMAIN}:admin_api_config"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        handler = _get_handler(request.app["hass"])
        return web.json_response(handler.data.get("config", {}))

    async def put(self, request: web.Request) -> web.Response:
        data = await request.json()
        handler = _get_handler(request.app["hass"])
        handler.data.setdefault("config", {}).update(data)
        await handler.async_save()
        return web.json_response({"success": True})


# --- PUBLIC API ENDPOINTS ---


class HelpView(HomeAssistantView):
    url = f"{API_PREFIX}/help"
    name = f"{DOMAIN}:help"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        ip = _get_client_ip(request)
        token = request.headers.get(HEADER_TOKEN_NAME)
        token_data = _find_token_data(hass, token) if token else None
        token_name = token_data.get("name", "") if token_data else ""
        await _track_usage(hass, token, "GET /help", 200, token_name=token_name, ip=ip)
        return web.json_response(API_HELP)


class StatesView(HomeAssistantView):
    url = f"{API_PREFIX}/states"
    name = f"{DOMAIN}:states"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)
        token_data, err = await _validate_token_request(hass, request, token, "GET /states")
        if err:
            return err

        incl_attrs = token_data.get("include_attributes", True)
        states = [
            _build_response(state, incl_attrs)
            for state in hass.states.async_all()
            if _is_entity_allowed(state.entity_id, token_data, hass)
        ]
        await _track_usage(
            hass,
            token,
            "GET /states",
            200,
            token_data.get("name", ""),
            ip=_get_client_ip(request),
        )
        return web.json_response(states)


class SingleStateView(HomeAssistantView):
    url = f"{API_PREFIX}/states/{{entity_id}}"
    name = f"{DOMAIN}:single_state"
    requires_auth = False

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)
        endpoint = f"GET /states/{entity_id}"
        token_data, err = await _validate_token_request(hass, request, token, endpoint)
        if err:
            return err

        if not _is_entity_allowed(entity_id, token_data, hass):
            await _track_usage(
                hass,
                token,
                endpoint,
                403,
                token_data.get("name", ""),
                ip=_get_client_ip(request),
            )
            return web.json_response({"error": "Forbidden"}, status=403)

        state = hass.states.get(entity_id)
        if not state:
            await _track_usage(
                hass,
                token,
                endpoint,
                404,
                token_data.get("name", ""),
                ip=_get_client_ip(request),
            )
            return web.json_response({"error": "Not found"}, status=404)

        incl_attrs = token_data.get("include_attributes", True)
        await _track_usage(
            hass,
            token,
            endpoint,
            200,
            token_data.get("name", ""),
            ip=_get_client_ip(request),
        )
        return web.json_response(_build_response(state, incl_attrs))


class EntityListView(HomeAssistantView):
    url = f"{API_PREFIX}/entities"
    name = f"{DOMAIN}:entities"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        token = request.headers.get(HEADER_TOKEN_NAME)
        token_data, err = await _validate_token_request(hass, request, token, "GET /entities")
        if err:
            return err

        entities = [
            s.entity_id
            for s in hass.states.async_all()
            if _is_entity_allowed(s.entity_id, token_data, hass)
        ]
        await _track_usage(
            hass,
            token,
            "GET /entities",
            200,
            token_data.get("name", ""),
            ip=_get_client_ip(request),
        )
        return web.json_response(entities)
