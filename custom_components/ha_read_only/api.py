# HA Read-Only API – Home Assistant Integration
# Copyright (c) 2026 T. Kuhn
# Lizenz: MIT – Siehe LICENSE-Datei im Repository
#
# DIE SOFTWARE WIRD "AS IS" BEREITGESTELLT, OHNE JEGLICHE GEWÄHRLEISTUNG.
# NUTZUNG AUF EIGENE GEFAHR.

from __future__ import annotations

import fnmatch
import ipaddress
import json
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

import hashlib
from unittest.mock import MagicMock, patch

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
    STATS_LOG_MAX,
    STATS_RETENTION_DAYS,
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
            "auth_required": True,
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

_ADMIN_HTML_PATH = os.path.join(os.path.dirname(__file__), "admin.html")


def _get_handler(hass: HomeAssistant) -> Any:
    return hass.data[DOMAIN]["handler"]


def _rate_limit_key(key: tuple[str, str]) -> str:
    return f"{key[0]}|{key[1]}"


def _rate_limit(hass: HomeAssistant, key: tuple[str, str], token_data: dict | None = None) -> bool:
    now = time.time()
    handler = _get_handler(hass)
    config = handler.data.get("config", {})
    window = config.get("rate_limit_window", RATE_LIMIT_WINDOW)
    max_limit = (
        config.get("rate_limit_max_per_ip", RATE_LIMIT_MAX_PER_IP)
        if key[0] == "ip"
        else config.get("rate_limit_max_per_token", RATE_LIMIT_MAX_PER_TOKEN)
    )
    if key[0] == "token" and token_data:
        token_max = token_data.get("rate_limit_max_requests")
        token_window_val = token_data.get("rate_limit_window_value")
        token_unit = token_data.get("rate_limit_window_unit")
        if token_max is not None and token_window_val and token_unit:
            max_limit = token_max
            unit_seconds = {"minutes": 60, "hours": 3600, "days": 86400}
            window = token_window_val * unit_seconds.get(token_unit, 3600)
    cache = handler.data.setdefault("rate_limit", {})
    cache_key = _rate_limit_key(key)
    records = [t for t in cache.get(cache_key, []) if t > now - window]
    if len(records) >= max_limit:
        return False
    records.append(now)
    cache[cache_key] = records
    return True


def _compute_hourly_chart(usage_log: list[dict]) -> list[int]:
    """Request counts per hour for the last 24 hours (fixed clock hours)."""
    now = time.time()
    now_hour = datetime.fromtimestamp(now).hour
    buckets = [0] * 24
    for entry in usage_log:
        ts = entry.get("timestamp")
        if not ts or now - ts > 86400:
            continue
        ts_hour = datetime.fromtimestamp(ts).hour
        idx = (ts_hour - now_hour + 23) % 24
        buckets[idx] += 1
    return buckets


def _compute_hourly_chart_by_color(usage_log: list[dict], tokens_map: dict) -> list[dict]:
    """Request counts per hour broken down by token color for the last 24 hours."""
    now = time.time()
    now_hour = datetime.fromtimestamp(now).hour
    buckets = []
    for _ in range(24):
        buckets.append({"total": 0, "by_color": {}})
    for entry in usage_log:
        ts = entry.get("timestamp")
        if not ts or now - ts > 86400:
            continue
        ts_hour = datetime.fromtimestamp(ts).hour
        idx = (ts_hour - now_hour + 23) % 24
        buckets[idx]["total"] += 1
        token_id = entry.get("token_id", "")
        token_data = tokens_map.get(token_id)
        color = token_data.get("color", "") if token_data else ""
        if color:
            buckets[idx]["by_color"][color] = buckets[idx]["by_color"].get(color, 0) + 1
        else:
            buckets[idx]["by_color"]["_default"] = buckets[idx]["by_color"].get("_default", 0) + 1
    return buckets


def _compute_daily_usage(usage_log: list[dict]) -> dict:
    """Request counts per day for the last 7 days, grouped by token_id."""
    now = time.time()
    daily = {}
    for entry in usage_log:
        ts = entry.get("timestamp")
        if not ts or now - ts > 7 * 86400:
            continue
        token_id = entry.get("token_id", "")
        if not token_id:
            continue
        day_idx = int((now - ts) / 86400)
        day_idx = min(6, day_idx)
        if token_id not in daily:
            daily[token_id] = [0] * 7
        daily[token_id][6 - day_idx] += 1
    return daily


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
    token_id: str = "",
    ip: str = "",
) -> None:
    handler = _get_handler(hass)
    stats = handler.data.setdefault("stats", {})
    key = token_id or (token or "no_token")
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
    token_data = _find_token_data(hass, token)
    config = handler.data.get("config", {})
    global_max = config.get("stats_log_max") if config.get("stats_log_max_enabled") else None
    if global_max is not None and entry["total"] >= global_max:
        return
    entry["total"] += 1
    entry["by_endpoint"][endpoint] = entry["by_endpoint"].get(endpoint, 0) + 1
    if status >= 400:
        entry["errors"] += 1
    entry["last_access"] = time.time()
    entry["last_endpoint"] = endpoint
    if token_name:
        entry["token_name"] = token_name
    if token_id and not entry.get("token_id"):
        entry["token_id"] = token_id
    if token_data and token_data.get("stats_retention_days"):
        entry["stats_retention_days"] = token_data["stats_retention_days"]

    log_entry = {
        "timestamp": time.time(),
        "ip": ip or "unknown",
        "endpoint": endpoint,
        "status": status,
        "token_name": token_name or (key[:8] + "..." if key != "no_token" else "—"),
        "token_id": token_id,
    }
    if status == 401:
        invalid_log = handler.data.setdefault("invalid_log", [])
        invalid_log.insert(0, log_entry)
        handler.data["invalid_log"] = invalid_log[:USAGE_LOG_MAX]
    else:
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


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _verify_token(plain_token: str, hashed_token: str) -> bool:
    return hashlib.sha256(plain_token.encode("utf-8")).hexdigest() == hashed_token


def _get_client_ip(request: web.Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    peer = request.transport.get_extra_info("peername")
    return peer[0] if peer else "unknown"


def _find_token_data(hass: HomeAssistant, token: str | None) -> dict | None:
    if not token:
        return None
    token_hash = _hash_token(token)
    for t in _get_handler(hass).data.get("tokens", []):
        if t.get("token_hash") == token_hash:
            return t
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


def _build_area_map(hass: HomeAssistant) -> dict[str, str | None]:
    """Einmaliger Durchlauf über alle States: entity_id → area_id."""
    registry = er.async_get(hass)
    return {
        s.entity_id: _get_area(registry, s.entity_id)
        for s in hass.states.async_all()
    }


def _get_area(registry: er.EntityRegistry, entity_id: str) -> str | None:
    entry = registry.async_get(entity_id)
    return entry.area_id if entry else None


def _is_entity_allowed(entity_id: str, token_data: dict, area_map: dict[str, str | None]) -> bool:
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
        area_id = area_map.get(entity_id)
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
        "color": data.get("color", ""),
        "rate_limit_max_requests": int(data["rate_limit_max_requests"]) if data.get("rate_limit_max_requests") else None,
        "rate_limit_window_value": int(data["rate_limit_window_value"]) if data.get("rate_limit_window_value") else None,
        "rate_limit_window_unit": data.get("rate_limit_window_unit") or None,
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

    token_data = _find_token_data(hass, token)
    if not token_data:
        await _track_usage(hass, token, endpoint, 401, ip=ip)
        return None, web.json_response({"error": "Invalid token"}, status=401)

    if not _is_token_valid(token_data):
        await _track_usage(
            hass, token, endpoint, 401, token_data.get("name", ""), token_id=token_data.get("id", ""), ip=ip
        )
        return None, web.json_response({"error": "Token expired"}, status=401)

    if not _rate_limit(hass, ("token", token), token_data):
        await _track_usage(
            hass, token, endpoint, 429, token_data.get("name", ""), token_id=token_data.get("id", ""), ip=ip
        )
        return None, web.json_response({"error": "Too many requests"}, status=429)

    if not _is_ip_allowed(ip, token_data.get("allowed_ips", [])):
        await _track_usage(
            hass, token, endpoint, 403, token_data.get("name", ""), token_id=token_data.get("id", ""), ip=ip
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
    hass.http.register_view(AdminApiTokenStatsView)
    hass.http.register_view(AdminApiStatsView)
    hass.http.register_view(AdminApiConfigView)
    hass.http.register_view(AdminApiStatsCleanupView)
    hass.http.register_view(AdminApiStatsLogDeleteView)
    hass.http.register_view(AdminApiTokenTestView)
    hass.http.register_view(AdminApiTokenCallView)
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
        hass = request.app["hass"]
        try:
            html = await hass.async_add_executor_job(self._read_admin_html)
        except Exception:
            html = "<html><body><h1>Error: admin.html not found</h1></body></html>"
        return web.Response(
            text=html,
            content_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    def _read_admin_html(self) -> str:
        with open(_ADMIN_HTML_PATH, "r", encoding="utf-8") as f:
            return f.read()


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
        stats = handler.data.get("stats", {})
        usage_log = handler.data.get("usage_log", [])
        daily_usage = _compute_daily_usage(usage_log)
        result = []
        for t in handler.data.get("tokens", []):
            token_stats = stats.get(t["id"], {})
            rl_max = t.get("rate_limit_max_requests")
            rl_window = t.get("rate_limit_window_value")
            rl_unit = t.get("rate_limit_window_unit")
            rate_limit_str = ""
            if rl_max:
                unit_labels = {"minutes": "Min.", "hours": "Std.", "days": "Tage"}
                if rl_window and rl_unit:
                    rate_limit_str = f"{rl_max}/{rl_window} {unit_labels.get(rl_unit, '')}"
                else:
                    rate_limit_str = f"{rl_max} (einmalig)"
            token_value = t.get(CONF_TOKEN, "") or t.get("token_hash", "")
            result.append({
                **t,
                "token_masked": _mask_token(token_value),
                "stats_total": token_stats.get("total", 0),
                "stats_errors": token_stats.get("errors", 0),
                "stats_last_access": token_stats.get("last_access"),
                "stats_last_endpoint": token_stats.get("last_endpoint"),
                "rate_limit_display": rate_limit_str,
                "daily_usage": daily_usage.get(t["id"], []),
            })
        return web.json_response(result)

    async def post(self, request: web.Request) -> web.Response:
        data = await request.json()
        token = secrets.token_urlsafe(32)
        new_token = {
            "id": secrets.token_hex(4),
            "token_hash": _hash_token(token),
            "created_at": time.time(),
            "regeneration_count": 0,
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
                t["token_hash"] = _hash_token(new_token)
                t["regeneration_count"] = t.get("regeneration_count", 0) + 1
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
        filter_id = request.query.get("token_id")
        tokens_map = {t["id"]: t for t in handler.data.get("tokens", [])}
        pie_data = []
        for k, v in stats.items():
            if v["total"] > 0:
                token_data = tokens_map.get(k)
                name = v.get("token_name")
                if not name:
                    name = k[:8] + "..."
                entry = {
                    "name": name,
                    "value": v["total"],
                    "color": token_data.get("color", "") if token_data else "",
                }
                pie_data.append(entry)
        if filter_id:
            usage_log = [e for e in usage_log if e.get("token_id") == filter_id]
            stats = {k: v for k, v in stats.items() if k == filter_id}
        total_requests = sum(s["total"] for s in stats.values())
        total_errors = sum(s["errors"] for s in stats.values())
        tokens_stats = [{**v, "token_key": k, "color": tokens_map.get(k, {}).get("color", "")} for k, v in stats.items()]
        tokens_map_for_chart = {t["id"]: t for t in handler.data.get("tokens", [])}
        for entry in usage_log:
            if not entry.get("token_name") or entry["token_name"] in ("—",):
                tid = entry.get("token_id", "")
                td = tokens_map.get(tid)
                if td and td.get("name"):
                    entry["token_name"] = td["name"]
        invalid_log = handler.data.get("invalid_log", [])
        return web.json_response(
            {
                "total_requests": total_requests,
                "total_errors": total_errors,
                "tokens": tokens_stats,
                "usage_log": usage_log,
                "invalid_log": invalid_log,
                "hourly": _compute_hourly_chart(usage_log),
                "hourly_by_color": _compute_hourly_chart_by_color(usage_log, tokens_map_for_chart),
                "pie": pie_data,
            }
        )


class AdminApiTokenStatsView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}/stats"
    name = f"{DOMAIN}:admin_api_token_stats"
    requires_auth = False

    async def put(self, request: web.Request, token_id: str) -> web.Response:
        data = await request.json()
        handler = _get_handler(request.app["hass"])
        for t in handler.data.get("tokens", []):
            if t["id"] == token_id:
                if "rate_limit_max_requests" in data:
                    t["rate_limit_max_requests"] = int(data["rate_limit_max_requests"]) if data["rate_limit_max_requests"] else None
                if "rate_limit_window_value" in data:
                    t["rate_limit_window_value"] = int(data["rate_limit_window_value"]) if data["rate_limit_window_value"] else None
                if "rate_limit_window_unit" in data:
                    t["rate_limit_window_unit"] = data["rate_limit_window_unit"] or None
                if "stats_retention_days" in data:
                    t["stats_retention_days"] = int(data["stats_retention_days"]) if data["stats_retention_days"] else None
                break
        await handler.async_save()
        return web.json_response({"success": True})


class AdminApiConfigView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/config"
    name = f"{DOMAIN}:admin_api_config"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        handler = _get_handler(request.app["hass"])
        cfg = handler.data.get("config", {})
        cfg.setdefault("stats_log_max", STATS_LOG_MAX)
        cfg.setdefault("stats_log_max_enabled", True)
        cfg.setdefault("stats_retention_days", STATS_RETENTION_DAYS)
        cfg.setdefault("stats_retention_enabled", True)
        return web.json_response(cfg)

    async def put(self, request: web.Request) -> web.Response:
        data = await request.json()
        handler = _get_handler(request.app["hass"])
        handler.data.setdefault("config", {}).update(data)
        await handler.async_save()
        return web.json_response({"success": True})


class AdminApiStatsCleanupView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/stats/cleanup"
    name = f"{DOMAIN}:admin_api_stats_cleanup"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        handler = _get_handler(request.app["hass"])
        usage_log = handler.data.get("usage_log", [])
        valid_log = [e for e in usage_log if e.get("token_id")]
        removed_log = len(usage_log) - len(valid_log)
        handler.data["usage_log"] = valid_log

        token_ids = {t["id"] for t in handler.data.get("tokens", [])}
        stats = handler.data.get("stats", {})
        valid_stats = {}
        removed_stats = 0
        for k, v in stats.items():
            if k in token_ids or k == "no_token":
                valid_stats[k] = v
            else:
                removed_stats += 1
        handler.data["stats"] = valid_stats

        await handler.async_save()
        return web.json_response({"removed_log": removed_log, "removed_stats": removed_stats, "remaining_log": len(valid_log)})

        await handler.async_save()
        return web.json_response({"removed_log": removed_log, "removed_stats": removed_stats, "remaining_log": len(valid_log)})


class AdminApiStatsLogDeleteView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/stats/log/{{index}}"
    name = f"{DOMAIN}:admin_api_stats_log_delete"
    requires_auth = False

    async def delete(self, request: web.Request, index: str) -> web.Response:
        handler = _get_handler(request.app["hass"])
        usage_log = handler.data.get("usage_log", [])
        try:
            idx = int(index)
            if 0 <= idx < len(usage_log):
                usage_log.pop(idx)
                handler.data["usage_log"] = usage_log
                await handler.async_save()
        except ValueError:
            pass
        return web.json_response({"success": True})


class AdminApiTokenTestView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}/test"
    name = f"{DOMAIN}:admin_api_token_test"
    requires_auth = False

    async def post(self, request: web.Request, token_id: str) -> web.Response:
        hass = request.app["hass"]
        handler = _get_handler(hass)
        token_data = next((t for t in handler.data.get("tokens", []) if t["id"] == token_id), None)

        if not token_data:
            return web.json_response({"error": "Token not found"}, status=404)

        tests = []
        area_map = _build_area_map(hass) if token_data.get("areas") else {}

        for test_fn in [
            self._test_token_validity,
            self._test_ip_whitelist,
            self._test_domains,
            self._test_areas,
            self._test_entities,
            self._test_patterns,
        ]:
            try:
                result = await test_fn(hass, token_data, request, area_map)
                tests.append(result)
            except Exception as e:
                tests.append({
                    "category": test_fn.__name__.replace("_test_", ""),
                    "label": result.get("label", test_fn.__name__) if isinstance(result, dict) else test_fn.__name__,
                    "status": "error",
                    "message": str(e),
                })

        passed = sum(1 for t in tests if t.get("status") == "pass")
        failed = sum(1 for t in tests if t.get("status") == "fail")
        skipped = sum(1 for t in tests if t.get("status") == "skip")

        return web.json_response({
            "token_name": token_data.get("name", "Unnamed"),
            "timestamp": time.time(),
            "tests": tests,
            "summary": {
                "total": len(tests),
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
        })

    async def _test_token_validity(self, hass, token_data, request, area_map) -> dict:
        result = {"category": "token_validity", "label": "Token-Gültigkeit", "details": []}
        result["details"].append({"check": "Token existiert", "status": "pass", "message": f"Name: {token_data.get('name', 'Unnamed')}"})
        if _is_token_valid(token_data):
            expires = token_data.get("expires_at")
            result["details"].append({"check": "Ablaufdatum", "status": "pass", "message": "Kein Ablauf" if expires is None else f"Ablauf: {datetime.fromtimestamp(float(expires)).strftime('%d.%m.%Y %H:%M')}"})
            result["status"] = "pass"
            result["message"] = "Token ist gültig"
        else:
            result["details"].append({"check": "Ablaufdatum", "status": "fail", "message": f"Token ist abgelaufen seit {datetime.fromtimestamp(float(token_data['expires_at'])).strftime('%d.%m.%Y %H:%M')}"})
            result["status"] = "fail"
            result["message"] = "Token ist abgelaufen"
        return result

    async def _test_ip_whitelist(self, hass, token_data, request, area_map) -> dict:
        result = {"category": "ip_whitelist", "label": "IP-Whitelist", "details": []}
        allowed_ips = token_data.get("allowed_ips", [])
        if not allowed_ips:
            result["status"] = "skip"
            result["message"] = "Keine IP-Whitelist konfiguriert"
            return result

        client_ip = _get_client_ip(request)
        for ip_entry in allowed_ips:
            ip_allowed = _is_ip_allowed(client_ip, [ip_entry])
            result["details"].append({
                "check": f"IP {ip_entry}",
                "status": "pass" if ip_allowed else "fail",
                "message": f"Client-IP {client_ip} ist {'erlaubt' if ip_allowed else 'blockiert'}",
            })

        test_ip = "10.255.255.255"
        if not _is_ip_allowed(test_ip, allowed_ips):
            result["details"].append({
                "check": "IP außerhalb",
                "status": "pass",
                "message": f"IP {test_ip} wird korrekt blockiert",
            })
        else:
            result["details"].append({
                "check": "IP außerhalb",
                "status": "info",
                "message": f"IP {test_ip} ist erlaubt (Whitelist ist sehr breit)",
            })

        has_fail = any(d["status"] == "fail" for d in result["details"])
        result["status"] = "fail" if has_fail else "pass"
        result["message"] = f"{len(allowed_ips)} IP-Regel(n) konfiguriert"
        return result

    async def _test_domains(self, hass, token_data, request, area_map) -> dict:
        result = {"category": "domains", "label": "Domain-Zugriff", "details": []}
        domains = token_data.get("domains", [])
        if not domains:
            result["status"] = "skip"
            result["message"] = "Keine Domains eingeschränkt"
            return result

        all_states = hass.states.async_all()
        all_domains = set(s.domain for s in all_states)

        for domain in domains:
            count = sum(1 for s in all_states if s.domain == domain)
            result["details"].append({
                "check": f"Domain: {domain}",
                "status": "pass",
                "message": f"{count} Entität(en) verfügbar",
            })

        blocked_domains = all_domains - set(domains)
        for domain in list(blocked_domains)[:3]:
            sample = next((s.entity_id for s in all_states if s.domain == domain), None)
            if sample and not _is_entity_allowed(sample, token_data, area_map):
                result["details"].append({
                    "check": f"Blockiert: {domain}",
                    "status": "pass",
                    "message": f"{sample} wird korrekt blockiert",
                })

        result["status"] = "pass"
        result["message"] = f"{len(domains)} Domain(s) geprüft"
        return result

    async def _test_areas(self, hass, token_data, request, area_map) -> dict:
        result = {"category": "areas", "label": "Bereichs-Zugriff", "details": []}
        areas = token_data.get("areas", [])
        if not areas:
            result["status"] = "skip"
            result["message"] = "Keine Bereiche eingeschränkt"
            return result

        area_reg = ar.async_get(hass)
        all_states = hass.states.async_all()

        for area_id in areas:
            area_name = area_id
            area_obj = area_reg.async_get_area(area_id)
            if area_obj:
                area_name = area_obj.name or area_id
            entities_in_area = [s.entity_id for s in all_states if area_map.get(s.entity_id) == area_id]
            if entities_in_area:
                allowed = sum(1 for eid in entities_in_area if _is_entity_allowed(eid, token_data, area_map))
                result["details"].append({
                    "check": f"Bereich: {area_name}",
                    "status": "pass" if allowed == len(entities_in_area) else "warn",
                    "message": f"{allowed}/{len(entities_in_area)} Entität(en) zugänglich",
                })
            else:
                result["details"].append({
                    "check": f"Bereich: {area_name}",
                    "status": "warn",
                    "message": "Keine Entitäten in diesem Bereich gefunden",
                })

        has_warn = any(d["status"] == "warn" for d in result["details"])
        result["status"] = "warn" if has_warn else "pass"
        result["message"] = f"{len(areas)} Bereich(e) geprüft"
        return result

    async def _test_entities(self, hass, token_data, request, area_map) -> dict:
        result = {"category": "entities", "label": "Entitäten-Zugriff", "details": []}
        allowed_entities = token_data.get("allowed_entities", [])
        if not allowed_entities:
            result["status"] = "skip"
            result["message"] = "Keine Einzel-Entitäten konfiguriert"
            return result

        for eid in allowed_entities:
            state = hass.states.get(eid)
            if not state:
                result["details"].append({
                    "check": eid,
                    "status": "fail",
                    "message": "Entität existiert nicht in Home Assistant",
                })
                continue
            allowed = _is_entity_allowed(eid, token_data, area_map)
            result["details"].append({
                "check": eid,
                "status": "pass" if allowed else "fail",
                "message": f"Status: {state.state}" if allowed else "Blockiert trotz Freigabe!",
            })

        has_fail = any(d["status"] == "fail" for d in result["details"])
        result["status"] = "fail" if has_fail else "pass"
        result["message"] = f"{len(allowed_entities)} Entität(en) geprüft"
        return result

    async def _test_patterns(self, hass, token_data, request, area_map) -> dict:
        result = {"category": "patterns", "label": "Pattern-Zugriff", "details": []}
        patterns = _to_pattern_list(token_data.get("patterns", ""))
        blocked_patterns = _to_pattern_list(token_data.get("blocked_patterns", ""))
        if not patterns and not blocked_patterns:
            result["status"] = "skip"
            result["message"] = "Keine Patterns konfiguriert"
            return result

        all_states = hass.states.async_all()
        for pat in patterns:
            matching = [s.entity_id for s in all_states if fnmatch.fnmatch(s.entity_id, pat)]
            if matching:
                allowed = sum(1 for eid in matching if _is_entity_allowed(eid, token_data, area_map))
                result["details"].append({
                    "check": f"Pattern: {pat}",
                    "status": "pass" if allowed else "fail",
                    "message": f"{allowed}/{len(matching)} Treffer zugänglich",
                })
            else:
                result["details"].append({
                    "check": f"Pattern: {pat}",
                    "status": "warn",
                    "message": "Keine passenden Entitäten gefunden",
                })

        for pat in blocked_patterns:
            matching = [s.entity_id for s in all_states if fnmatch.fnmatch(s.entity_id, pat)]
            blocked = sum(1 for eid in matching if not _is_entity_allowed(eid, token_data, area_map))
            result["details"].append({
                "check": f"Block-Pattern: {pat}",
                "status": "pass" if blocked == len(matching) else "fail",
                "message": f"{blocked}/{len(matching)} Treffer korrekt blockiert" if matching else "Keine passenden Entitäten",
            })

        has_fail = any(d["status"] == "fail" for d in result["details"])
        result["status"] = "fail" if has_fail else "pass"
        result["message"] = f"{len(patterns)} Allow- + {len(blocked_patterns)} Block-Pattern(s) geprüft"
        return result


class AdminApiTokenCallView(HomeAssistantView):
    url = f"{API_PREFIX}/admin/api/tokens/{{token_id}}/test/call"
    name = f"{DOMAIN}:admin_api_token_call"
    requires_auth = False

    async def post(self, request: web.Request, token_id: str) -> web.Response:
        hass = request.app["hass"]
        handler = _get_handler(hass)
        token_data = next((t for t in handler.data.get("tokens", []) if t["id"] == token_id), None)
        if not token_data:
            return web.json_response({"error": "Token not found"}, status=404)

        body = await request.json()
        endpoint = body.get("endpoint", "")
        entity_id = body.get("entity_id", "")
        test_ip = body.get("test_ip", "")

        mock_req = MagicMock(spec=web.Request)
        mock_req.headers = {HEADER_TOKEN_NAME: "__test__"}
        mock_req.app = {"hass": hass}
        mock_req.method = "GET"
        mock_req.query = {}
        transport = MagicMock()
        transport.get_extra_info.return_value = (test_ip or "127.0.0.1", 0)
        mock_req.transport = transport

        def _fake_find(hass, token):
            return token_data

        start = time.time()
        try:
            view = None
            path = API_PREFIX
            if endpoint == "states":
                view = StatesView()
                path += "/states"
            elif endpoint == "entities":
                view = EntityListView()
                path += "/entities"
            elif endpoint == "help":
                view = HelpView()
                path += "/help"
            elif endpoint == "state":
                if not entity_id:
                    return web.json_response({"error": "entity_id required"}, status=400)
                view = SingleStateView()
                path += f"/states/{entity_id}"
            else:
                return web.json_response({"error": f"Unknown endpoint: {endpoint}"}, status=400)

            mock_req.path = path
            with patch("custom_components.ha_read_only.api._find_token_data", _fake_find):
                if endpoint == "state":
                    resp = await view.get(mock_req, entity_id)
                else:
                    resp = await view.get(mock_req)

            elapsed = round((time.time() - start) * 1000, 1)
            resp_body = json.loads(resp.body) if resp.body else None
            return web.json_response({
                "status": resp.status,
                "time_ms": elapsed,
                "body": resp_body,
            })
        except Exception as e:
            elapsed = round((time.time() - start) * 1000, 1)
            return web.json_response({
                "status": 500,
                "time_ms": elapsed,
                "error": str(e),
            })


# --- PUBLIC API ENDPOINTS ---


class HelpView(HomeAssistantView):
    url = f"{API_PREFIX}/help"
    name = f"{DOMAIN}:help"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        ip = _get_client_ip(request)
        token = request.headers.get(HEADER_TOKEN_NAME)
        token_data, err = await _validate_token_request(hass, request, token, "GET /help")
        if err:
            return err
        token_name = token_data.get("name", "")
        token_id = token_data.get("id", "")
        await _track_usage(hass, token, "GET /help", 200, token_name=token_name, token_id=token_id, ip=ip)
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
        area_map = _build_area_map(hass) if token_data.get("areas") else {}
        states = [
            _build_response(state, incl_attrs)
            for state in hass.states.async_all()
            if _is_entity_allowed(state.entity_id, token_data, area_map)
        ]
        await _track_usage(
            hass,
            token,
            "GET /states",
            200,
            token_data.get("name", ""),
            token_id=token_data.get("id", ""),
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

        area_map = _build_area_map(hass) if token_data.get("areas") else {}
        if not _is_entity_allowed(entity_id, token_data, area_map):
            await _track_usage(
                hass,
                token,
                endpoint,
                403,
                token_data.get("name", ""),
                token_id=token_data.get("id", ""),
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
                token_id=token_data.get("id", ""),
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
            token_id=token_data.get("id", ""),
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

        area_map = _build_area_map(hass) if token_data.get("areas") else {}
        entities = [
            s.entity_id
            for s in hass.states.async_all()
            if _is_entity_allowed(s.entity_id, token_data, area_map)
        ]
        await _track_usage(
            hass,
            token,
            "GET /entities",
            200,
            token_data.get("name", ""),
            token_id=token_data.get("id", ""),
            ip=_get_client_ip(request),
        )
        return web.json_response(entities)
