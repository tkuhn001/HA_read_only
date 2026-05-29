from __future__ import annotations

import json
import time
import secrets
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest
from aiohttp import web

from custom_components.ha_read_only.api import (
    AdminApiTokensView,
    AdminApiTokenView,
    AdminApiTokenRegenerateView,
    AdminApiOptionsView,
    AdminApiEntitiesView,
    AdminApiStatsView,
    AdminApiTokenStatsView,
    AdminApiConfigView,
    AdminApiStatsCleanupView,
    AdminApiStatsLogDeleteView,
    AdminApiTokenTestView,
    AdminPanelView,
    _hash_token,
    _compute_daily_usage,
)
from custom_components.ha_read_only.const import DOMAIN, HEADER_TOKEN_NAME


@pytest.fixture
def mock_handler():
    """Create a handler with pre-populated data."""
    handler = MagicMock()
    token1_id = secrets.token_hex(4)
    token2_id = secrets.token_hex(4)
    handler.data = {
        "tokens": [
            {
                "id": token1_id,
                "token_hash": _hash_token("token-1-value"),
                "name": "Token 1",
                "created_at": time.time() - 86400,
                "domains": ["sensor"],
                "patterns": "",
                "blocked_patterns": "",
                "include_attributes": True,
                "expires_at": None,
                "areas": [],
                "allowed_ips": [],
                "allowed_entities": [],
                "color": "blue",
                "rate_limit_max_requests": None,
                "rate_limit_window_value": None,
                "rate_limit_window_unit": None,
            },
            {
                "id": token2_id,
                "token_hash": _hash_token("token-2-value"),
                "name": "Token 2",
                "created_at": time.time(),
                "domains": ["light"],
                "patterns": "switch.*",
                "blocked_patterns": "",
                "include_attributes": False,
                "expires_at": time.time() + 86400,
                "areas": ["area_living"],
                "allowed_ips": ["10.0.0.0/24"],
                "allowed_entities": [],
                "color": "red",
                "rate_limit_max_requests": 100,
                "rate_limit_window_value": 5,
                "rate_limit_window_unit": "minutes",
            },
        ],
        "stats": {
            token1_id: {
                "token_name": "Token 1",
                "total": 50,
                "by_endpoint": {"GET /states": 30, "GET /entities": 20},
                "errors": 2,
                "last_access": time.time() - 3600,
                "last_endpoint": "GET /entities",
            },
            token2_id: {
                "token_name": "Token 2",
                "total": 10,
                "by_endpoint": {"GET /states": 10},
                "errors": 0,
                "last_access": time.time() - 1800,
                "last_endpoint": "GET /states",
            },
        },
        "config": {
            "rate_limit_window": 60,
            "rate_limit_max_per_ip": 100,
            "rate_limit_max_per_token": 500,
            "webhook_url": "",
            "stats_log_max": 500,
            "stats_log_max_enabled": True,
            "stats_retention_days": 30,
            "stats_retention_enabled": True,
        },
        "usage_log": [
            {"timestamp": time.time() - 100, "ip": "10.0.0.1", "endpoint": "GET /states", "status": 200, "token_name": "Token 1", "token_id": token1_id},
            {"timestamp": time.time() - 200, "ip": "10.0.0.2", "endpoint": "GET /entities", "status": 200, "token_name": "Token 2", "token_id": token2_id},
        ],
        "rate_limit": {},
        "invalid_log": [],
    }
    handler.async_save = AsyncMock()
    return handler, token1_id, token2_id


# ========== AdminApiTokensView - GET ==========


async def test_tokens_get_returns_all_tokens_with_masked_values(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiTokensView()
        resp = await view.get(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert len(body) == 2
        for t in body:
            assert "token_masked" in t
        t1 = next(t for t in body if t["id"] == token1_id)
        assert t1["token_masked"].endswith("...")
        assert t1["token_masked"] == t1["token_hash"][:8] + "..."
        t2 = next(t for t in body if t["id"] == token2_id)
        assert t2["token_masked"].endswith("...")
        assert t2["token_masked"] == t2["token_hash"][:8] + "..."


async def test_tokens_get_returns_stats_per_token(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiTokensView()
        resp = await view.get(req)
        body = json.loads(resp.body)
        t1 = next(t for t in body if t["id"] == token1_id)
        assert t1["stats_total"] == 50
        assert t1["stats_errors"] == 2
        assert isinstance(t1["stats_last_access"], float)
        assert t1["stats_last_endpoint"] == "GET /entities"
        t2 = next(t for t in body if t["id"] == token2_id)
        assert t2["stats_total"] == 10
        assert t2["stats_errors"] == 0
        assert t2["stats_last_endpoint"] == "GET /states"


async def test_tokens_get_returns_rate_limit_display(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiTokensView()
        resp = await view.get(req)
        body = json.loads(resp.body)
        t1 = next(t for t in body if t["id"] == token1_id)
        assert t1["rate_limit_display"] == ""
        t2 = next(t for t in body if t["id"] == token2_id)
        assert t2["rate_limit_display"] == "100/5 Min."


async def test_tokens_get_returns_daily_usage(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiTokensView()
        resp = await view.get(req)
        body = json.loads(resp.body)
        t1 = next(t for t in body if t["id"] == token1_id)
        t2 = next(t for t in body if t["id"] == token2_id)
        assert isinstance(t1["daily_usage"], list)
        assert len(t1["daily_usage"]) == 7
        assert isinstance(t2["daily_usage"], list)
        assert len(t2["daily_usage"]) == 7


# ========== AdminApiTokensView - POST (create token) ==========


async def test_tokens_post_creates_token_minimal(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with (
        patch("custom_components.ha_read_only.api._get_handler", return_value=handler),
        patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()),
    ):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"name": "New Token"})
        view = AdminApiTokensView()
        resp = await view.post(req)
        assert resp.status == 201
        body = json.loads(resp.body)
        assert "token" in body
        assert isinstance(body["token"], str)
        assert len(body["token"]) > 0
        assert "id" in body
        assert isinstance(body["id"], str)
        assert len(handler.data["tokens"]) == 3
        new_token = handler.data["tokens"][2]
        assert new_token["name"] == "New Token"
        assert new_token["token_hash"] == _hash_token(body["token"])
        handler.async_save.assert_called_once()


async def test_tokens_post_stores_hash_and_fires_webhook(mock_handler):
    handler, token1_id, token2_id = mock_handler
    mock_webhook = AsyncMock()
    with (
        patch("custom_components.ha_read_only.api._get_handler", return_value=handler),
        patch("custom_components.ha_read_only.api._fire_webhook", mock_webhook),
    ):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"name": "Webhook Token"})
        view = AdminApiTokensView()
        resp = await view.post(req)
        assert resp.status == 201
        body = json.loads(resp.body)
        assert handler.data["tokens"][2]["token_hash"] == _hash_token(body["token"])
        assert handler.data["tokens"][2].get("token", None) is None
        mock_webhook.assert_called_once()
        args, _ = mock_webhook.call_args
        assert args[1] == "token_created"
        assert args[2]["token_name"] == "Webhook Token"


async def test_tokens_post_full_data(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with (
        patch("custom_components.ha_read_only.api._get_handler", return_value=handler),
        patch("custom_components.ha_read_only.api._fire_webhook", AsyncMock()),
    ):
        full_data = {
            "name": "Full Token",
            "domains": ["sensor", "light"],
            "patterns": "switch.*\ncover.*",
            "blocked_patterns": "sensor.secret_*",
            "include_attributes": False,
            "expires_at": time.time() + 3600,
            "areas": ["area_living", "area_kitchen"],
            "allowed_ips": "10.0.0.0/24\n192.168.1.0/24",
            "allowed_entities": ["switch.test"],
            "color": "green",
            "rate_limit_max_requests": 50,
            "rate_limit_window_value": 10,
            "rate_limit_window_unit": "hours",
        }
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value=full_data)
        view = AdminApiTokensView()
        resp = await view.post(req)
        assert resp.status == 201
        new_token = handler.data["tokens"][2]
        assert new_token["name"] == "Full Token"
        assert new_token["domains"] == ["sensor", "light"]
        assert isinstance(new_token["patterns"], str)
        assert "switch.*" in new_token["patterns"]
        assert "cover.*" in new_token["patterns"]
        assert new_token["include_attributes"] is False
        assert new_token["expires_at"] is not None
        assert "area_living" in new_token["areas"]
        assert "10.0.0.0/24" in new_token["allowed_ips"]
        assert new_token["color"] == "green"
        assert new_token["rate_limit_max_requests"] == 50
        assert new_token["rate_limit_window_value"] == 10
        assert new_token["rate_limit_window_unit"] == "hours"
        assert new_token["regeneration_count"] == 0


# ========== AdminApiTokenView - PUT (update token) ==========


async def test_token_put_updates_existing(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"name": "Updated Token 1", "color": "yellow"})
        view = AdminApiTokenView()
        resp = await view.put(req, token1_id)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
        assert t1["name"] == "Updated Token 1"
        assert t1["color"] == "yellow"
        handler.async_save.assert_called_once()


async def test_token_put_non_existent(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"name": "Ghost"})
        view = AdminApiTokenView()
        resp = await view.put(req, "non-existent-id")
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        assert len(handler.data["tokens"]) == 2
        handler.async_save.assert_called_once()


async def test_token_put_partial_update(mock_handler):
    handler, token1_id, token2_id = mock_handler
    original_t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"name": "Just Name"})
        view = AdminApiTokenView()
        resp = await view.put(req, token1_id)
        assert resp.status == 200
        t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
        assert t1["name"] == "Just Name"
        assert t1["domains"] == []
        assert t1["patterns"] == ""
        assert t1["blocked_patterns"] == ""
        assert t1["color"] == ""
        assert t1["include_attributes"] is True
        assert t1["rate_limit_max_requests"] is None
        assert t1["rate_limit_window_value"] is None
        assert t1["rate_limit_window_unit"] is None


async def test_token_put_clears_expires_at(mock_handler):
    handler, token1_id, token2_id = mock_handler
    t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
    t1["expires_at"] = 9999999999.0
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"expires_at": None})
        view = AdminApiTokenView()
        resp = await view.put(req, token1_id)
        assert resp.status == 200
        t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
        assert t1["expires_at"] is None


# ========== AdminApiTokenView - DELETE ==========


async def test_token_delete_existing(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiTokenView()
        resp = await view.delete(req, token1_id)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        assert len(handler.data["tokens"]) == 1
        assert handler.data["tokens"][0]["id"] == token2_id
        handler.async_save.assert_called_once()


async def test_token_delete_non_existent(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiTokenView()
        resp = await view.delete(req, "non-existent-id")
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        assert len(handler.data["tokens"]) == 2


# ========== AdminApiTokenRegenerateView - POST ==========


async def test_token_regenerate_existing(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiTokenRegenerateView()
        old_hash = next(t for t in handler.data["tokens"] if t["id"] == token1_id)["token_hash"]
        resp = await view.post(req, token1_id)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert "token" in body
        t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
        assert t1["token_hash"] != old_hash
        assert t1["token_hash"] == _hash_token(body["token"])
        assert t1["regeneration_count"] == 1
        handler.async_save.assert_called_once()


async def test_token_regenerate_non_existent(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiTokenRegenerateView()
        old_hashes = [t["token_hash"] for t in handler.data["tokens"]]
        resp = await view.post(req, "non-existent-id")
        assert resp.status == 200
        body = json.loads(resp.body)
        assert "token" in body
        current_hashes = [t["token_hash"] for t in handler.data["tokens"]]
        assert current_hashes == old_hashes
        handler.async_save.assert_called_once()


# ========== AdminApiOptionsView - GET ==========


async def test_options_get_returns_domains_and_areas():
    hass = MagicMock()
    state1 = MagicMock(domain="sensor")
    state2 = MagicMock(domain="light")
    state3 = MagicMock(domain="sensor")
    hass.states.async_all.return_value = [state1, state2, state3]

    with patch("custom_components.ha_read_only.api.ar.async_get") as mock_ar_get:
        mock_area_reg = MagicMock()
        area1 = MagicMock()
        area1.id = "area_living"
        area1.name = "Living Room"
        area2 = MagicMock()
        area2.id = "area_bath"
        area2.name = None
        mock_area_reg.areas = {"area_living": area1, "area_bath": area2}
        mock_ar_get.return_value = mock_area_reg

        req = MagicMock(spec=web.Request)
        req.app = {"hass": hass}
        view = AdminApiOptionsView()
        resp = await view.get(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["domains"] == ["light", "sensor"]
        assert len(body["areas"]) == 2
        area_ids = [a["id"] for a in body["areas"]]
        assert "area_living" in area_ids
        assert "area_bath" in area_ids


# ========== AdminApiEntitiesView - GET ==========


async def test_entities_get_returns_all_sorted():
    hass = MagicMock()
    entities = ["switch.b", "sensor.a", "light.c"]
    hass.states.async_all.return_value = [
        MagicMock(entity_id=e) for e in entities
    ]
    req = MagicMock(spec=web.Request)
    req.app = {"hass": hass}
    req.query = {}
    view = AdminApiEntitiesView()
    resp = await view.get(req)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body == ["light.c", "sensor.a", "switch.b"]


async def test_entities_get_filters_by_query():
    hass = MagicMock()
    entities = ["sensor.temperature", "sensor.humidity", "light.living_room"]
    hass.states.async_all.return_value = [
        MagicMock(entity_id=e) for e in entities
    ]
    req = MagicMock(spec=web.Request)
    req.app = {"hass": hass}
    req.query = {"q": "temp"}
    view = AdminApiEntitiesView()
    resp = await view.get(req)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body == ["sensor.temperature"]


async def test_entities_get_filters_case_insensitive():
    hass = MagicMock()
    entities = ["sensor.Temperature", "sensor.Humidity"]
    hass.states.async_all.return_value = [
        MagicMock(entity_id=e) for e in entities
    ]
    req = MagicMock(spec=web.Request)
    req.app = {"hass": hass}
    req.query = {"q": "emp"}
    view = AdminApiEntitiesView()
    resp = await view.get(req)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert body == ["sensor.Temperature"]


async def test_entities_get_returns_all_without_hard_limit():
    hass = MagicMock()
    entities = [f"sensor.test_{i}" for i in range(200)]
    hass.states.async_all.return_value = [
        MagicMock(entity_id=e) for e in entities
    ]
    req = MagicMock(spec=web.Request)
    req.app = {"hass": hass}
    req.query = {}
    view = AdminApiEntitiesView()
    resp = await view.get(req)
    assert resp.status == 200
    body = json.loads(resp.body)
    assert len(body) == 200


# ========== AdminApiStatsView - GET ==========


async def test_stats_get_returns_totals(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiStatsView()
        resp = await view.get(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["total_requests"] == 60
        assert body["total_errors"] == 2


async def test_stats_get_returns_hourly_chart(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiStatsView()
        resp = await view.get(req)
        body = json.loads(resp.body)
        assert "hourly" in body
        assert isinstance(body["hourly"], list)
        assert len(body["hourly"]) == 24
        assert all(isinstance(v, int) for v in body["hourly"])
        assert "hourly_by_color" in body
        assert isinstance(body["hourly_by_color"], list)
        assert len(body["hourly_by_color"]) == 24
        for bucket in body["hourly_by_color"]:
            assert "total" in bucket
            assert "by_color" in bucket


async def test_stats_get_returns_pie_chart(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiStatsView()
        resp = await view.get(req)
        body = json.loads(resp.body)
        assert "pie" in body
        assert isinstance(body["pie"], list)
        assert len(body["pie"]) == 2
        pie_names = {p["name"] for p in body["pie"]}
        assert "Token 1" in pie_names
        assert "Token 2" in pie_names
        for p in body["pie"]:
            assert "value" in p
            assert "color" in p
            assert p["value"] > 0


async def test_stats_get_filters_by_token_id(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {"token_id": token1_id}
        view = AdminApiStatsView()
        resp = await view.get(req)
        body = json.loads(resp.body)
        assert body["total_requests"] == 50
        assert body["total_errors"] == 2
        assert len(body["tokens"]) == 1
        assert len(body["usage_log"]) == 1
        assert body["usage_log"][0]["token_id"] == token1_id


async def test_stats_get_usage_log_resolves_token_names(mock_handler):
    handler, token1_id, token2_id = mock_handler
    handler.data["usage_log"] = [
        {"timestamp": time.time(), "ip": "1.2.3.4", "endpoint": "GET /test", "status": 200, "token_name": "", "token_id": token1_id},
        {"timestamp": time.time(), "ip": "1.2.3.5", "endpoint": "GET /test2", "status": 200, "token_name": "—", "token_id": token2_id},
    ]
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.query = {}
        view = AdminApiStatsView()
        resp = await view.get(req)
        body = json.loads(resp.body)
        assert body["usage_log"][0]["token_name"] == "Token 1"
        assert body["usage_log"][1]["token_name"] == "Token 2"


# ========== AdminApiTokenStatsView - PUT ==========


async def test_token_stats_put_updates_rate_limit(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={
            "rate_limit_max_requests": 200,
            "rate_limit_window_value": 15,
            "rate_limit_window_unit": "minutes",
        })
        view = AdminApiTokenStatsView()
        resp = await view.put(req, token1_id)
        assert resp.status == 200
        t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
        assert t1["rate_limit_max_requests"] == 200
        assert t1["rate_limit_window_value"] == 15
        assert t1["rate_limit_window_unit"] == "minutes"
        handler.async_save.assert_called_once()


async def test_token_stats_put_updates_retention_days(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"stats_retention_days": 60})
        view = AdminApiTokenStatsView()
        resp = await view.put(req, token1_id)
        assert resp.status == 200
        t1 = next(t for t in handler.data["tokens"] if t["id"] == token1_id)
        assert t1["stats_retention_days"] == 60


async def test_token_stats_put_clears_rate_limit(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={
            "rate_limit_max_requests": None,
            "rate_limit_window_value": None,
            "rate_limit_window_unit": None,
        })
        view = AdminApiTokenStatsView()
        resp = await view.put(req, token2_id)
        assert resp.status == 200
        t2 = next(t for t in handler.data["tokens"] if t["id"] == token2_id)
        assert t2["rate_limit_max_requests"] is None
        assert t2["rate_limit_window_value"] is None
        assert t2["rate_limit_window_unit"] is None


async def test_token_stats_put_non_existent(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"rate_limit_max_requests": 999})
        view = AdminApiTokenStatsView()
        resp = await view.put(req, "non-existent-id")
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        handler.async_save.assert_called_once()


# ========== AdminApiConfigView - GET ==========


async def test_config_get_returns_with_defaults_set():
    handler = MagicMock()
    handler.data = {"config": {}}
    handler.async_save = AsyncMock()
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiConfigView()
        resp = await view.get(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["stats_log_max"] == 500
        assert body["stats_log_max_enabled"] is True
        assert body["stats_retention_days"] == 30
        assert body["stats_retention_enabled"] is True


async def test_config_get_without_overriding_existing():
    handler = MagicMock()
    handler.data = {
        "config": {
            "rate_limit_window": 120,
            "stats_log_max": 1000,
            "stats_log_max_enabled": False,
        }
    }
    handler.async_save = AsyncMock()
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiConfigView()
        resp = await view.get(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["rate_limit_window"] == 120
        assert body["stats_log_max"] == 1000
        assert body["stats_log_max_enabled"] is False
        assert body["stats_retention_days"] == 30
        assert body["stats_retention_enabled"] is True


# ========== AdminApiConfigView - PUT ==========


async def test_config_put_updates_config(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"rate_limit_window": 300, "webhook_url": "http://example.com"})
        view = AdminApiConfigView()
        resp = await view.put(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        assert handler.data["config"]["rate_limit_window"] == 300
        assert handler.data["config"]["webhook_url"] == "http://example.com"
        handler.async_save.assert_called_once()


async def test_config_put_merges_with_existing(mock_handler):
    handler, token1_id, token2_id = mock_handler
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        req.json = AsyncMock(return_value={"webhook_url": "http://hook.dev"})
        view = AdminApiConfigView()
        resp = await view.put(req)
        assert resp.status == 200
        assert handler.data["config"]["rate_limit_window"] == 60
        assert handler.data["config"]["webhook_url"] == "http://hook.dev"
        assert handler.data["config"]["rate_limit_max_per_ip"] == 100


# ========== AdminApiStatsCleanupView - POST ==========


async def test_stats_cleanup_removes_orphaned_stats(mock_handler):
    handler, token1_id, token2_id = mock_handler
    handler.data["stats"]["orphaned_key"] = {
        "token_name": "Orphan",
        "total": 5,
        "by_endpoint": {},
        "errors": 0,
        "last_access": None,
        "last_endpoint": None,
    }
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiStatsCleanupView()
        resp = await view.post(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["removed_stats"] == 1
        assert "orphaned_key" not in handler.data["stats"]
        assert token1_id in handler.data["stats"]
        assert token2_id in handler.data["stats"]
        handler.async_save.assert_called_once()


async def test_stats_cleanup_removes_orphaned_log_entries(mock_handler):
    handler, token1_id, token2_id = mock_handler
    handler.data["usage_log"].append({
        "timestamp": time.time(), "ip": "1.2.3.4", "endpoint": "GET /x", "status": 200,
        "token_name": "Orphan", "token_id": "",
    })
    handler.data["usage_log"].append({
        "timestamp": time.time(), "ip": "1.2.3.5", "endpoint": "GET /y", "status": 200,
        "token_name": "Ghost", "token_id": None,
    })
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiStatsCleanupView()
        resp = await view.post(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["removed_log"] == 2
        assert body["remaining_log"] == 2


async def test_stats_cleanup_returns_counts(mock_handler):
    handler, token1_id, token2_id = mock_handler
    handler.data["stats"]["no_token"] = {"total": 1, "errors": 0, "by_endpoint": {}, "last_access": None, "last_endpoint": None}
    handler.data["usage_log"].append({
        "timestamp": time.time(), "ip": "1.2.3.4", "endpoint": "GET /orphan", "status": 200,
        "token_name": "", "token_id": "",
    })
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiStatsCleanupView()
        resp = await view.post(req)
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["removed_log"] == 1
        assert body["removed_stats"] == 0
        assert body["remaining_log"] == 2
        assert "no_token" in handler.data["stats"]


# ========== AdminApiStatsLogDeleteView - DELETE ==========


async def test_stats_log_delete_deletes_by_index(mock_handler):
    handler, token1_id, token2_id = mock_handler
    initial_len = len(handler.data["usage_log"])
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiStatsLogDeleteView()
        resp = await view.delete(req, "0")
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        assert len(handler.data["usage_log"]) == initial_len - 1
        handler.async_save.assert_called_once()


async def test_stats_log_delete_invalid_index_out_of_range(mock_handler):
    handler, token1_id, token2_id = mock_handler
    initial_log = list(handler.data["usage_log"])
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiStatsLogDeleteView()
        resp = await view.delete(req, "999")
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        assert handler.data["usage_log"] == initial_log
        handler.async_save.assert_not_called()


async def test_stats_log_delete_invalid_index_non_numeric(mock_handler):
    handler, token1_id, token2_id = mock_handler
    initial_log = list(handler.data["usage_log"])
    with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
        req = MagicMock(spec=web.Request)
        req.app = {"hass": MagicMock()}
        view = AdminApiStatsLogDeleteView()
        resp = await view.delete(req, "abc")
        assert resp.status == 200
        body = json.loads(resp.body)
        assert body["success"] is True
        assert handler.data["usage_log"] == initial_log
        handler.async_save.assert_not_called()


class TestAdminApiTokenTest:
    """Tests for the AdminApiTokenTestView endpoint."""

    @pytest.mark.asyncio
    async def test_token_not_found(self, mock_handler):
        handler, token1_id, token2_id = mock_handler
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            req = MagicMock(spec=web.Request)
            req.app = {"hass": MagicMock()}
            view = AdminApiTokenTestView()
            resp = await view.post(req, "non_existent_id")
            assert resp.status == 404
            body = json.loads(resp.body)
            assert body["error"] == "Token not found"

    @pytest.mark.asyncio
    async def test_token_test_returns_summary(self, mock_handler):
        handler, token1_id, token2_id = mock_handler
        hass = MagicMock()
        hass.data = {}
        hass.states = MagicMock()
        hass.states.async_all = MagicMock(return_value=[])
        handler.data["tokens"][0]["expires_at"] = time.time() + 86400
        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler):
            req = MagicMock(spec=web.Request)
            req.app = {"hass": hass}
            req.headers = {}
            transport = MagicMock()
            transport.get_extra_info.return_value = ("127.0.0.1", 0)
            req.transport = transport
            view = AdminApiTokenTestView()
            resp = await view.post(req, token1_id)
            assert resp.status == 200
            body = json.loads(resp.body)
            assert body["token_name"] == "Token 1"
            assert "summary" in body
            assert body["summary"]["total"] > 0
            assert body["summary"]["passed"] + body["summary"]["failed"] + body["summary"]["skipped"] == body["summary"]["total"]

    @pytest.mark.asyncio
    async def test_token_test_with_features(self, mock_handler):
        handler, token1_id, token2_id = mock_handler
        hass = MagicMock()
        hass.data = {}

        s1 = MagicMock()
        s1.entity_id = "sensor.temp"
        s1.state = "22"
        s1.domain = "sensor"
        s1.attributes = {}
        hass.states.async_all = MagicMock(return_value=[s1])

        handler.data["tokens"][0].update({
            "expires_at": time.time() + 86400,
            "domains": ["sensor"],
            "areas": [],
            "allowed_entities": [],
            "patterns": "",
            "blocked_patterns": "",
            "allowed_ips": ["10.0.0.0/24"],
        })

        with patch("custom_components.ha_read_only.api._get_handler", return_value=handler), \
             patch("custom_components.ha_read_only.api.er") as mock_er:
            registry = MagicMock()
            entry = MagicMock()
            entry.area_id = None
            registry.async_get = MagicMock(return_value=entry)
            mock_er.async_get = MagicMock(return_value=registry)

            req = MagicMock(spec=web.Request)
            req.app = {"hass": hass}
            req.headers = {}
            transport = MagicMock()
            transport.get_extra_info.return_value = ("10.0.0.5", 0)
            req.transport = transport
            view = AdminApiTokenTestView()
            resp = await view.post(req, token1_id)
            assert resp.status == 200
            body = json.loads(resp.body)
            assert body["summary"]["total"] > 0
            passed_or_skipped = body["summary"]["passed"] + body["summary"]["skipped"]
            assert passed_or_skipped >= body["summary"]["total"] - body["summary"]["failed"]


# ========== AdminPanelView ==========


class TestAdminPanelView:
    async def test_returns_html(self):
        hass = MagicMock()

        async def _run(fn, *a, **kw):
            return fn(*a, **kw)

        hass.async_add_executor_job.side_effect = _run
        with patch("custom_components.ha_read_only.api.AdminPanelView._read_admin_html",
                   return_value="<html>test {VERSION}</html>"):
            view = AdminPanelView()
            req = MagicMock(spec=web.Request)
            req.app = {"hass": hass}
            resp = await view.get(req)
        assert resp.status == 200
        assert resp.content_type == "text/html"
        assert resp.text == "<html>test {VERSION}</html>"

    async def test_fallback_on_file_error(self):
        hass = MagicMock()

        async def _run(fn, *a, **kw):
            return fn(*a, **kw)

        hass.async_add_executor_job.side_effect = _run
        with patch("custom_components.ha_read_only.api.AdminPanelView._read_admin_html",
                   side_effect=Exception("no file")):
            view = AdminPanelView()
            req = MagicMock(spec=web.Request)
            req.app = {"hass": hass}
            resp = await view.get(req)
        assert resp.status == 200
        assert "Error: admin.html not found" in resp.text
