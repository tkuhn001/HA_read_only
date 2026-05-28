from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from custom_components.ha_read_only.api import (
    EntityListView,
    HelpView,
    SingleStateView,
    StatesView,
)
from custom_components.ha_read_only.const import (
    API_PREFIX,
    DOMAIN,
    HEADER_TOKEN_NAME,
)


@pytest.fixture
def mock_hass():
    """Mock HomeAssistant with handler, states, and a valid token."""
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "handler": MagicMock(),
        }
    }
    handler = hass.data[DOMAIN]["handler"]
    handler.data = {
        "tokens": [
            {
                "id": "tok1",
                "name": "Test Token",
                "token_hash": "b4c9a2b5c8d1e3f7a6b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9",
                "domains": [],
                "patterns": "",
                "blocked_patterns": "",
                "include_attributes": True,
                "expires_at": None,
                "areas": [],
                "allowed_ips": [],
                "allowed_entities": [],
            }
        ],
        "stats": {},
        "config": {
            "rate_limit_window": 60,
            "rate_limit_max_per_ip": 1000,
            "rate_limit_max_per_token": 1000,
        },
        "usage_log": [],
        "rate_limit": {},
    }
    handler.async_save = AsyncMock()

    s1 = MagicMock()
    s1.entity_id = "sensor.temperature"
    s1.state = "23.5"
    s1.attributes = {"unit_of_measurement": "\u00b0C", "friendly_name": "Temperature"}

    s2 = MagicMock()
    s2.entity_id = "light.living_room"
    s2.state = "on"
    s2.attributes = {"brightness": 200, "friendly_name": "Living Room Light"}

    s3 = MagicMock()
    s3.entity_id = "switch.denied"
    s3.state = "off"
    s3.attributes = {"friendly_name": "Denied Switch"}

    hass.states.async_all = MagicMock(return_value=[s1, s2, s3])
    hass.states.get = MagicMock(
        side_effect=lambda eid: {
            "sensor.temperature": s1,
            "light.living_room": s2,
            "switch.denied": s3,
        }.get(eid)
    )

    return hass


@pytest.fixture
def mock_request():
    """Factory that creates a mock aiohttp request with a given token header."""
    def _make(token_value=None, method="GET", path="/", ip="10.0.0.1"):
        req = MagicMock()
        headers = {}
        if token_value is not None:
            headers[HEADER_TOKEN_NAME] = token_value
        req.headers = headers
        req.method = method
        req.path = path
        transport = MagicMock()
        transport.get_extra_info.return_value = (ip, 0)
        req.transport = transport
        return req
    return _make


# ---------------------------------------------------------------------------
# HelpView – GET /api/ha_read_only/help
# ---------------------------------------------------------------------------


class TestHelpView:
    async def test_get_help_with_valid_token(self, mock_hass, mock_request):
        view = HelpView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = ({"name": "Test Token", "id": "tok1"}, None)

            response = await view.get(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert data["name"] == "HA Read-Only API"
            assert data["read_only"] is True
            assert len(data["endpoints"]) == 4
            mock_val.assert_called_once()
            mock_track.assert_called_once()

    async def test_get_help_with_invalid_token(self, mock_hass, mock_request):
        view = HelpView()
        request = mock_request(token_value="bad-token")
        request.app = {"hass": mock_hass}

        with patch(
            "custom_components.ha_read_only.api._validate_token_request",
        ) as mock_val:
            mock_val.return_value = (
                None,
                web.json_response({"error": "Invalid token"}, status=401),
            )

            response = await view.get(request)

        assert response.status == 401
        data = json.loads(response.body)
        assert data["error"] == "Invalid token"

    def test_view_attributes(self):
        view = HelpView()
        assert view.url == f"{API_PREFIX}/help"
        assert view.name == f"{DOMAIN}:help"
        assert view.requires_auth is False


# ---------------------------------------------------------------------------
# StatesView – GET /api/ha_read_only/states
# ---------------------------------------------------------------------------


class TestStatesView:
    async def test_get_states_with_valid_token(self, mock_hass, mock_request):
        view = StatesView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Test Token",
            "id": "tok1",
            "include_attributes": True,
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = True

            response = await view.get(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert len(data) == 3
            assert data[0]["entity_id"] == "sensor.temperature"
            assert data[0]["state"] == "23.5"
            assert "attributes" in data[0]
            assert data[1]["entity_id"] == "light.living_room"
            assert data[2]["entity_id"] == "switch.denied"
            mock_track.assert_called_once()

    async def test_get_states_filters_by_entity_allowed(
        self, mock_hass, mock_request,
    ):
        view = StatesView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Filtered Token",
            "id": "tok1",
            "include_attributes": True,
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)

            def side_effect(entity_id, token_data, hass):
                return entity_id in ("sensor.temperature", "light.living_room")

            mock_allowed.side_effect = side_effect

            response = await view.get(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert len(data) == 2
            assert data[0]["entity_id"] == "sensor.temperature"
            assert data[1]["entity_id"] == "light.living_room"

    async def test_get_states_without_attributes(self, mock_hass, mock_request):
        view = StatesView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "No Attributes Token",
            "id": "tok1",
            "include_attributes": False,
            "domains": [],
            "patterns": "",
            "blocked_patterns": "",
            "areas": [],
            "allowed_entities": [],
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = True

            response = await view.get(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert len(data) == 3
            for entry in data:
                assert "entity_id" in entry
                assert "state" in entry
                assert "attributes" not in entry

    async def test_get_states_no_token(self, mock_hass, mock_request):
        view = StatesView()
        request = mock_request(token_value=None)
        request.app = {"hass": mock_hass}

        with patch(
            "custom_components.ha_read_only.api._validate_token_request",
        ) as mock_val:
            mock_val.return_value = (
                None,
                web.json_response({"error": "Invalid token"}, status=401),
            )

            response = await view.get(request)

        assert response.status == 401
        data = json.loads(response.body)
        assert data["error"] == "Invalid token"

    async def test_get_states_token_expired(self, mock_hass, mock_request):
        view = StatesView()
        request = mock_request(token_value="expired-token")
        request.app = {"hass": mock_hass}

        with patch(
            "custom_components.ha_read_only.api._validate_token_request",
        ) as mock_val:
            mock_val.return_value = (
                None,
                web.json_response({"error": "Token expired"}, status=401),
            )

            response = await view.get(request)

        assert response.status == 401
        data = json.loads(response.body)
        assert data["error"] == "Token expired"

    async def test_get_states_rate_limited(self, mock_hass, mock_request):
        view = StatesView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        with patch(
            "custom_components.ha_read_only.api._validate_token_request",
        ) as mock_val:
            mock_val.return_value = (
                None,
                web.json_response({"error": "Too many requests"}, status=429),
            )

            response = await view.get(request)

        assert response.status == 429
        data = json.loads(response.body)
        assert data["error"] == "Too many requests"

    def test_view_attributes(self):
        view = StatesView()
        assert view.url == f"{API_PREFIX}/states"
        assert view.name == f"{DOMAIN}:states"
        assert view.requires_auth is False


# ---------------------------------------------------------------------------
# SingleStateView – GET /api/ha_read_only/states/{entity_id}
# ---------------------------------------------------------------------------


class TestSingleStateView:
    async def test_get_allowed_entity(self, mock_hass, mock_request):
        view = SingleStateView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Test Token",
            "id": "tok1",
            "include_attributes": True,
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage"),
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = True

            response = await view.get(request, "sensor.temperature")

            assert response.status == 200
            data = json.loads(response.body)
            assert data["entity_id"] == "sensor.temperature"
            assert data["state"] == "23.5"
            assert data["attributes"] == {
                "unit_of_measurement": "\u00b0C",
                "friendly_name": "Temperature",
            }

    async def test_get_allowed_entity_without_attributes(
        self, mock_hass, mock_request,
    ):
        view = SingleStateView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Test Token",
            "id": "tok1",
            "include_attributes": False,
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage"),
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = True

            response = await view.get(request, "light.living_room")

            assert response.status == 200
            data = json.loads(response.body)
            assert data["entity_id"] == "light.living_room"
            assert data["state"] == "on"
            assert "attributes" not in data

    async def test_get_not_allowed_entity(self, mock_hass, mock_request):
        view = SingleStateView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Test Token",
            "id": "tok1",
            "include_attributes": True,
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = False

            response = await view.get(request, "switch.denied")

        assert response.status == 403
        data = json.loads(response.body)
        assert data["error"] == "Forbidden"
        mock_track.assert_called_once()

    async def test_get_nonexistent_entity(self, mock_hass, mock_request):
        view = SingleStateView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Test Token",
            "id": "tok1",
            "include_attributes": True,
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = True

            response = await view.get(request, "sensor.nonexistent")

        assert response.status == 404
        data = json.loads(response.body)
        assert data["error"] == "Not found"
        mock_track.assert_called_once()

    async def test_get_with_invalid_token(self, mock_hass, mock_request):
        view = SingleStateView()
        request = mock_request(token_value="bad-token")
        request.app = {"hass": mock_hass}

        with patch(
            "custom_components.ha_read_only.api._validate_token_request",
        ) as mock_val:
            mock_val.return_value = (
                None,
                web.json_response({"error": "Invalid token"}, status=401),
            )

            response = await view.get(request, "sensor.temperature")

        assert response.status == 401
        data = json.loads(response.body)
        assert data["error"] == "Invalid token"

    def test_view_attributes(self):
        view = SingleStateView()
        assert view.url == f"{API_PREFIX}/states/{{entity_id}}"
        assert view.name == f"{DOMAIN}:single_state"
        assert view.requires_auth is False


# ---------------------------------------------------------------------------
# EntityListView – GET /api/ha_read_only/entities
# ---------------------------------------------------------------------------


class TestEntityListView:
    async def test_get_entities_with_valid_token(self, mock_hass, mock_request):
        view = EntityListView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Test Token",
            "id": "tok1",
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = True

            response = await view.get(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert isinstance(data, list)
            assert len(data) == 3
            assert "sensor.temperature" in data
            assert "light.living_room" in data
            assert "switch.denied" in data
            mock_track.assert_called_once()

    async def test_get_entities_filtered(self, mock_hass, mock_request):
        view = EntityListView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Filtered Token",
            "id": "tok1",
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)

            def side_effect(entity_id, token_data, hass):
                return entity_id == "light.living_room"

            mock_allowed.side_effect = side_effect

            response = await view.get(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert data == ["light.living_room"]
            mock_track.assert_called_once()

    async def test_get_entities_empty(self, mock_hass, mock_request):
        view = EntityListView()
        request = mock_request(token_value="valid-token")
        request.app = {"hass": mock_hass}

        token_data = {
            "name": "Empty Token",
            "id": "tok1",
        }

        with (
            patch(
                "custom_components.ha_read_only.api._validate_token_request",
            ) as mock_val,
            patch(
                "custom_components.ha_read_only.api._is_entity_allowed",
            ) as mock_allowed,
            patch("custom_components.ha_read_only.api._track_usage") as mock_track,
        ):
            mock_val.return_value = (token_data, None)
            mock_allowed.return_value = False

            response = await view.get(request)

            assert response.status == 200
            data = json.loads(response.body)
            assert data == []
            mock_track.assert_called_once()

    async def test_get_entities_with_invalid_token(self, mock_hass, mock_request):
        view = EntityListView()
        request = mock_request(token_value="bad-token")
        request.app = {"hass": mock_hass}

        with patch(
            "custom_components.ha_read_only.api._validate_token_request",
        ) as mock_val:
            mock_val.return_value = (
                None,
                web.json_response({"error": "Invalid token"}, status=401),
            )

            response = await view.get(request)

        assert response.status == 401
        data = json.loads(response.body)
        assert data["error"] == "Invalid token"

    def test_view_attributes(self):
        view = EntityListView()
        assert view.url == f"{API_PREFIX}/entities"
        assert view.name == f"{DOMAIN}:entities"
        assert view.requires_auth is False
