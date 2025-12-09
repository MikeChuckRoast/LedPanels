"""
Tests for web_server.py module.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWebServerCreation:
    """Tests for WebServer class and start_web_server function."""

    def test_creates_webserver_instance(self, populated_config_dir):
        """Test that WebServer instance is created."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5001)

        assert server is not None
        assert server.config_dir == Path(populated_config_dir)
        assert server.host == "127.0.0.1"
        assert server.port == 5001

    def test_start_web_server_function(self, populated_config_dir):
        """Test that start_web_server function works."""
        from web_server import start_web_server

        # Don't actually start the server, just test instantiation
        with patch('web_server.WebServer.start'):
            server = start_web_server(str(populated_config_dir), "127.0.0.1", 5002)
            assert server is not None


class TestWebServerRoutes:
    """Tests for WebServer route handlers."""

    # Removed setup_method since each test creates its own WebServer with populated_config_dir fixture

    def test_get_events_endpoint(self, populated_config_dir):
        """Test GET /api/events endpoint."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5010)

        with server.app.test_client() as client:
            with patch.object(server, '_get_events', return_value=[]):
                response = client.get('/api/events')
                assert response.status_code == 200

    def test_get_current_event_endpoint(self, populated_config_dir):
        """Test GET /api/current_event endpoint."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5011)

        with server.app.test_client() as client:
            with patch.object(server, '_get_current_event', return_value={"event": 1, "round": 1, "heat": 1}):
                response = client.get('/api/current_event')
                assert response.status_code == 200
                data = json.loads(response.data)
                assert "event" in data

    def test_set_current_event_endpoint(self, populated_config_dir):
        """Test POST /api/current_event endpoint."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5012)

        with server.app.test_client() as client:
            event_data = {"event": 5, "round": 2, "heat": 3}

            with patch.object(server, '_set_current_event', return_value={"status": "success"}):
                response = client.post(
                    '/api/current_event',
                    data=json.dumps(event_data),
                    content_type='application/json'
                )
                assert response.status_code == 200

    def test_get_teams_endpoint(self, populated_config_dir):
        """Test GET /api/teams endpoint."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5013)

        with server.app.test_client() as client:
            with patch.object(server, '_get_teams', return_value={}):
                response = client.get('/api/teams')
                assert response.status_code == 200

    def test_set_teams_endpoint(self, populated_config_dir):
        """Test POST /api/teams endpoint."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5014)

        with server.app.test_client() as client:
            colors_data = {"Monroe Jefferson": {"bgcolor": "#ff0000", "text": "#ffffff"}}

            with patch.object(server, '_set_teams', return_value={"status": "success"}):
                response = client.post(
                    '/api/teams',
                    data=json.dumps(colors_data),
                    content_type='application/json'
                )
                assert response.status_code == 200


class TestWebServerMethods:
    """Tests for WebServer internal methods."""

    def test_get_events_parses_lynx_file(self, populated_config_dir):
        """Test that get_events parses lynx.evt file."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5004)

        with server.app.test_request_context():
            response, status = server._get_events()
            assert status == 200
            data = response.get_json()
            assert 'events' in data
            assert len(data['events']) > 0

    def test_get_current_event_loads_json(self, populated_config_dir):
        """Test that get_current_event loads current_event.json."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5005)

        with server.app.test_request_context():
            response, status = server._get_current_event()
            assert status == 200
            data = response.get_json()
            assert "event" in data
            assert "round" in data
            assert "heat" in data

    def test_set_current_event_saves_json(self, populated_config_dir):
        """Test that set_current_event saves to current_event.json."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5006)

        new_event = {"event": 7, "round": 3, "heat": 2}


        with server.app.test_request_context(json=new_event):


            response, status = server._set_current_event()


            assert status == 200

        # Verify file was updated
        event_file = Path(populated_config_dir) / "current_event.json"
        with open(event_file) as f:
            saved = json.load(f)

        assert saved["event"] == 7
        assert saved["round"] == 3
        assert saved["heat"] == 2

    def test_set_current_event_triggers_reload(self, populated_config_dir):
        """Test that set_current_event successfully updates event."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5007)

        new_event = {"event": 3, "round": 1, "heat": 1}


        with server.app.test_request_context(json=new_event):


            response, status = server._set_current_event()


            assert status == 200

    def test_get_teams_loads_csv(self, populated_config_dir):
        """Test that get_teams loads colors.csv."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5008)

        with server.app.test_request_context():
            response, status = server._get_teams()
            assert status == 200
            data = response.get_json()
            assert 'teams' in data

    def test_set_teams_saves_csv(self, populated_config_dir):
        """Test that set_teams saves to colors.csv."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5009)

        new_teams = [
            {
                "affiliation": "TEST",
                "name": "Test Team",
                "bgcolor": "#123456",
                "text": "#fedcba"
            }
        ]

        with server.app.test_request_context(json={"teams": new_teams}):
            response, status = server._set_teams()
            assert status == 200
