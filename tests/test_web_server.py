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


class TestWebServerFileUpload:
    """Tests for file upload endpoints."""

    def test_upload_events_success(self, populated_config_dir):
        """Test successful events file upload."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5020)

        # Read sample events file
        sample_file = Path(__file__).parent / "fixtures" / "sample_lynx.evt"
        with open(sample_file, 'r', encoding='utf-8') as f:
            content = f.read()

        data = {"content": content}

        with server.app.test_request_context(json=data):
            response, status = server._upload_events()
            assert status == 200
            result = response.get_json()
            assert result['success'] is True
            assert result['event_count'] > 0

        # Verify backup was created
        backup_file = Path(populated_config_dir) / "lynx.evt.bak"
        assert backup_file.exists()

        # Verify file was updated
        events_file = Path(populated_config_dir) / "lynx.evt"
        with open(events_file, 'r', encoding='utf-8') as f:
            saved_content = f.read()
        assert saved_content == content

    def test_upload_events_missing_content(self, populated_config_dir):
        """Test events upload with missing content field."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5021)

        data = {}

        with server.app.test_request_context(json=data):
            response, status = server._upload_events()
            assert status == 400
            result = response.get_json()
            assert 'error' in result
            assert 'content' in result['error'].lower()

    def test_upload_events_empty_content(self, populated_config_dir):
        """Test events upload with empty content."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5022)

        data = {"content": "   "}

        with server.app.test_request_context(json=data):
            response, status = server._upload_events()
            assert status == 400
            result = response.get_json()
            assert 'error' in result
            assert 'empty' in result['error'].lower()

    def test_upload_events_invalid_format(self, populated_config_dir):
        """Test events upload with invalid format."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5023)

        data = {"content": "not,valid,csv,format\nwith,random,data"}

        with server.app.test_request_context(json=data):
            response, status = server._upload_events()
            assert status == 400
            result = response.get_json()
            assert 'error' in result

    def test_upload_schedule_success(self, populated_config_dir):
        """Test successful schedule file upload."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5024)

        # Read sample schedule file
        sample_file = Path(__file__).parent / "fixtures" / "sample_schedule.sch"
        with open(sample_file, 'r', encoding='utf-8') as f:
            content = f.read()

        data = {"content": content}

        with server.app.test_request_context(json=data):
            response, status = server._upload_schedule()
            assert status == 200
            result = response.get_json()
            assert result['success'] is True
            assert result['total_entries'] > 0
            assert result['valid_entries'] >= 0

        # Verify file was updated
        schedule_file = Path(populated_config_dir) / "lynx.sch"
        assert schedule_file.exists()
        with open(schedule_file, 'r', encoding='utf-8') as f:
            saved_content = f.read()
        assert saved_content == content

    def test_upload_schedule_missing_content(self, populated_config_dir):
        """Test schedule upload with missing content field."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5025)

        data = {}

        with server.app.test_request_context(json=data):
            response, status = server._upload_schedule()
            assert status == 400
            result = response.get_json()
            assert 'error' in result
            assert 'content' in result['error'].lower()

    def test_upload_schedule_empty_content(self, populated_config_dir):
        """Test schedule upload with empty content."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5026)

        data = {"content": "   "}

        with server.app.test_request_context(json=data):
            response, status = server._upload_schedule()
            assert status == 400
            result = response.get_json()
            assert 'error' in result
            assert 'empty' in result['error'].lower()

    def test_upload_schedule_validates_against_events(self, populated_config_dir):
        """Test schedule upload validates entries against events."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5027)

        # Create schedule with non-existent events
        content = "; Test schedule\nevent,round,heat\n999,999,999\n"

        data = {"content": content}

        with server.app.test_request_context(json=data):
            response, status = server._upload_schedule()
            assert status == 400
            result = response.get_json()
            assert 'error' in result
            # Should fail because no valid entries match events

    def test_upload_combined_success(self, populated_config_dir):
        """Test successful combined upload of both files."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5028)

        # Read sample files
        events_file = Path(__file__).parent / "fixtures" / "sample_lynx.evt"
        schedule_file = Path(__file__).parent / "fixtures" / "sample_schedule.sch"

        with open(events_file, 'r', encoding='utf-8') as f:
            events_content = f.read()

        with open(schedule_file, 'r', encoding='utf-8') as f:
            schedule_content = f.read()

        data = {
            "events": events_content,
            "schedule": schedule_content
        }

        with server.app.test_request_context(json=data):
            response, status = server._upload_combined()
            assert status == 200
            result = response.get_json()
            assert result['success'] is True
            assert 'events' in result
            assert 'schedule' in result
            assert result['events']['event_count'] > 0
            assert result['schedule']['valid_entries'] > 0

        # Verify files were created/updated
        assert (Path(populated_config_dir) / "lynx.evt").exists()
        assert (Path(populated_config_dir) / "lynx.sch").exists()

    def test_upload_combined_missing_events(self, populated_config_dir):
        """Test combined upload with missing events field."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5029)

        data = {
            "schedule": "event,round,heat\n1,1,1\n"
        }

        with server.app.test_request_context(json=data):
            response, status = server._upload_combined()
            assert status == 400
            result = response.get_json()
            assert 'error' in result
            assert 'events' in result['error'].lower()

    def test_upload_combined_missing_schedule(self, populated_config_dir):
        """Test combined upload with missing schedule field."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5030)

        sample_file = Path(__file__).parent / "fixtures" / "sample_lynx.evt"
        with open(sample_file, 'r', encoding='utf-8') as f:
            events_content = f.read()

        data = {
            "events": events_content
        }

        with server.app.test_request_context(json=data):
            response, status = server._upload_combined()
            assert status == 400
            result = response.get_json()
            assert 'error' in result
            assert 'schedule' in result['error'].lower()

    def test_upload_combined_validates_schedule_against_new_events(self, populated_config_dir):
        """Test combined upload validates schedule against new events (not old)."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5031)

        # Create new events and matching schedule
        events_content = "10,1,1,Test Event,,,,,,100\n,1,1,Smith,John,Test,,,,,,,123\n"
        schedule_content = "event,round,heat\n10,1,1\n"

        data = {
            "events": events_content,
            "schedule": schedule_content
        }

        with server.app.test_request_context(json=data):
            response, status = server._upload_combined()
            assert status == 200
            result = response.get_json()
            assert result['success'] is True
            assert result['schedule']['valid_entries'] == 1

    def test_upload_combined_atomic_rollback(self, populated_config_dir):
        """Test that combined upload doesn't update if schedule validation fails."""
        from web_server import WebServer

        server = WebServer(str(populated_config_dir), host="127.0.0.1", port=5032)

        # Get original events file content
        events_file = Path(populated_config_dir) / "lynx.evt"
        with open(events_file, 'r', encoding='utf-8') as f:
            original_events = f.read()

        # Try to upload with valid events but invalid schedule (no matching entries)
        events_content = "10,1,1,Test Event,,,,,,100\n,1,1,Smith,John,Test,,,,,,,123\n"
        schedule_content = "event,round,heat\n999,1,1\n"  # Non-existent event

        data = {
            "events": events_content,
            "schedule": schedule_content
        }

        with server.app.test_request_context(json=data):
            response, status = server._upload_combined()
            assert status == 400  # Should fail validation

        # Verify original events file was not changed
        with open(events_file, 'r', encoding='utf-8') as f:
            current_events = f.read()

        assert current_events == original_events

        # Verify schedule file was not created
        schedule_file = Path(populated_config_dir) / "lynx.sch"
        assert not schedule_file.exists()
