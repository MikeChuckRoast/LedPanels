"""
Web server for LED display control interface.

Provides a Flask-based web interface for:
- Viewing and selecting events from lynx.evt
- Editing team colors in colors.csv
- Adjusting display settings in settings.toml
"""

import csv
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import toml
from flask import Flask, jsonify, render_template, request, send_from_directory

from event_parser import (load_affiliation_colors, parse_hex_color,
                          parse_lynx_file)
from schedule_parser import parse_schedule, validate_schedule_entries


class WebServer:
    """Web server for LED display control interface."""

    def __init__(self, config_dir: str, host: str = "0.0.0.0", port: int = 5000):
        """Initialize web server.

        Args:
            config_dir: Path to configuration directory
            host: Host to bind to
            port: Port to listen on
        """
        self.config_dir = Path(config_dir)
        self.host = host
        self.port = port
        self.app = Flask(__name__,
                        static_folder='static',
                        template_folder='templates')
        self.server_thread = None

        # Register routes
        self._register_routes()

        # Disable Flask's default logging to avoid clutter
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.WARNING)

    def _register_routes(self):
        """Register all Flask routes."""

        # Static pages
        @self.app.route('/')
        def index():
            return send_from_directory('static', 'index.html')

        @self.app.route('/teams')
        def teams():
            return send_from_directory('static', 'teams.html')

        @self.app.route('/display')
        def display():
            return send_from_directory('static', 'display.html')

        # API endpoints
        @self.app.route('/api/events', methods=['GET'])
        def get_events():
            return self._get_events()

        @self.app.route('/api/current_event', methods=['GET'])
        def get_current_event():
            return self._get_current_event()

        @self.app.route('/api/current_event', methods=['POST'])
        def set_current_event():
            return self._set_current_event()

        @self.app.route('/api/teams', methods=['GET'])
        def get_teams():
            return self._get_teams()

        @self.app.route('/api/teams', methods=['POST'])
        def set_teams():
            return self._set_teams()

        @self.app.route('/api/display_settings', methods=['GET'])
        def get_display_settings():
            return self._get_display_settings()

        @self.app.route('/api/display_settings', methods=['POST'])
        def set_display_settings():
            return self._set_display_settings()

    def _get_events(self) -> Tuple[Dict, int]:
        """Get list of events from lynx.evt file.

        Returns:
            JSON response with events list and status code
        """
        try:
            lynx_file = self.config_dir / "lynx.evt"
            events = parse_lynx_file(str(lynx_file))

            # Try to load schedule for ordering
            schedule_path = self.config_dir / "lynx.sch"
            schedule = []
            if schedule_path.exists():
                try:
                    raw_schedule = parse_schedule(schedule_path)
                    schedule = validate_schedule_entries(raw_schedule, events)
                except Exception as e:
                    logging.warning(f"Failed to load schedule for web API: {e}")

            # Convert to list format for JSON
            events_list = []
            scheduled_keys = set()

            if schedule:
                # Add scheduled events in order with position numbers
                for idx, (event_num, round_num, heat_num) in enumerate(schedule):
                    key = (event_num, round_num, heat_num)
                    scheduled_keys.add(key)
                    event_data = events[key]
                    events_list.append({
                        'event': event_num,
                        'round': round_num,
                        'heat': heat_num,
                        'name': event_data['name'],
                        'athlete_count': len(event_data['athletes']),
                        'schedule_position': idx + 1,
                        'total_scheduled': len(schedule)
                    })

                # Add unscheduled events at the end (sorted)
                for (event_num, round_num, heat_num), event_data in sorted(events.items()):
                    key = (event_num, round_num, heat_num)
                    if key not in scheduled_keys:
                        events_list.append({
                            'event': event_num,
                            'round': round_num,
                            'heat': heat_num,
                            'name': event_data['name'],
                            'athlete_count': len(event_data['athletes']),
                            'schedule_position': None,
                            'total_scheduled': None
                        })
            else:
                # No schedule - use default sorting
                for (event_num, round_num, heat_num), event_data in sorted(events.items()):
                    events_list.append({
                        'event': event_num,
                        'round': round_num,
                        'heat': heat_num,
                        'name': event_data['name'],
                        'athlete_count': len(event_data['athletes']),
                        'schedule_position': None,
                        'total_scheduled': None
                    })

            return jsonify({'events': events_list, 'has_schedule': len(schedule) > 0}), 200
        except FileNotFoundError:
            return jsonify({'error': 'lynx.evt file not found'}), 404
        except Exception as e:
            logging.error(f"Error loading events: {e}")
            return jsonify({'error': str(e)}), 500

    def _get_current_event(self) -> Tuple[Dict, int]:
        """Get current event selection from current_event.json.

        Returns:
            JSON response with current event and status code
        """
        try:
            current_event_file = self.config_dir / "current_event.json"
            with open(current_event_file, 'r', encoding='utf-8') as f:
                current_event = json.load(f)
            return jsonify(current_event), 200
        except FileNotFoundError:
            return jsonify({'error': 'current_event.json file not found'}), 404
        except json.JSONDecodeError as e:
            return jsonify({'error': f'Invalid JSON format: {e}'}), 400
        except Exception as e:
            logging.error(f"Error loading current event: {e}")
            return jsonify({'error': str(e)}), 500

    def _set_current_event(self) -> Tuple[Dict, int]:
        """Set current event selection in current_event.json.

        Expects JSON body with 'event', 'round', 'heat' fields.

        Returns:
            JSON response with success/error and status code
        """
        try:
            data = request.get_json()

            # Validate required fields
            if not all(k in data for k in ['event', 'round', 'heat']):
                return jsonify({'error': 'Missing required fields: event, round, heat'}), 400

            # Validate types and values
            try:
                event_num = int(data['event'])
                round_num = int(data['round'])
                heat_num = int(data['heat'])

                if event_num < 1 or round_num < 1 or heat_num < 1:
                    return jsonify({'error': 'Event, round, and heat must be positive integers'}), 400
            except (ValueError, TypeError):
                return jsonify({'error': 'Event, round, and heat must be integers'}), 400

            # Write to file
            current_event_file = self.config_dir / "current_event.json"
            current_event = {
                'event': event_num,
                'round': round_num,
                'heat': heat_num
            }

            with open(current_event_file, 'w', encoding='utf-8') as f:
                json.dump(current_event, f, indent=2)

            logging.info(f"Updated current event to: Event={event_num}, Round={round_num}, Heat={heat_num}")
            return jsonify({'success': True, 'current_event': current_event}), 200

        except Exception as e:
            logging.error(f"Error setting current event: {e}")
            return jsonify({'error': str(e)}), 500

    def _get_teams(self) -> Tuple[Dict, int]:
        """Get team color mappings from colors.csv.

        Returns:
            JSON response with teams list and status code
        """
        try:
            colors_file = self.config_dir / "colors.csv"
            teams = []

            with open(colors_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    teams.append({
                        'affiliation': row.get('affiliation', ''),
                        'name': row.get('name', ''),
                        'bgcolor': row.get('bgcolor', ''),
                        'text': row.get('text', '')
                    })

            return jsonify({'teams': teams}), 200
        except FileNotFoundError:
            return jsonify({'error': 'colors.csv file not found'}), 404
        except Exception as e:
            logging.error(f"Error loading teams: {e}")
            return jsonify({'error': str(e)}), 500

    def _set_teams(self) -> Tuple[Dict, int]:
        """Set team color mappings in colors.csv.

        Expects JSON body with 'teams' array containing team objects.

        Returns:
            JSON response with success/error and status code
        """
        try:
            data = request.get_json()

            if 'teams' not in data or not isinstance(data['teams'], list):
                return jsonify({'error': 'Missing or invalid teams array'}), 400

            teams = data['teams']

            # Validate each team
            for i, team in enumerate(teams):
                # Check required fields
                if not all(k in team for k in ['affiliation', 'name', 'bgcolor', 'text']):
                    return jsonify({'error': f'Team {i}: Missing required fields'}), 400

                # Validate affiliation is not empty
                if not team['affiliation'].strip():
                    return jsonify({'error': f'Team {i}: Affiliation cannot be empty'}), 400

                # Validate color formats
                for color_field in ['bgcolor', 'text']:
                    try:
                        parse_hex_color(team[color_field])
                    except ValueError as e:
                        return jsonify({'error': f'Team {i} ({team["affiliation"]}): Invalid {color_field}: {e}'}), 400

            # Write to CSV file
            colors_file = self.config_dir / "colors.csv"
            with open(colors_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['affiliation', 'name', 'bgcolor', 'text'])
                writer.writeheader()
                writer.writerows(teams)

            logging.info(f"Updated team colors: {len(teams)} teams saved")
            return jsonify({'success': True, 'count': len(teams)}), 200

        except Exception as e:
            logging.error(f"Error setting teams: {e}")
            return jsonify({'error': str(e)}), 500

    def _get_display_settings(self) -> Tuple[Dict, int]:
        """Get display settings from settings.toml.

        Returns:
            JSON response with display settings and status code
        """
        try:
            settings_file = self.config_dir / "settings.toml"
            with open(settings_file, 'r', encoding='utf-8') as f:
                config = toml.load(f)

            display_settings = config.get('display', {})
            return jsonify({'display': display_settings}), 200
        except FileNotFoundError:
            return jsonify({'error': 'settings.toml file not found'}), 404
        except Exception as e:
            logging.error(f"Error loading display settings: {e}")
            return jsonify({'error': str(e)}), 500

    def _set_display_settings(self) -> Tuple[Dict, int]:
        """Set display settings in settings.toml [display] section.

        Expects JSON body with 'display' object containing settings.

        Returns:
            JSON response with success/error and status code
        """
        try:
            data = request.get_json()

            if 'display' not in data or not isinstance(data['display'], dict):
                return jsonify({'error': 'Missing or invalid display settings object'}), 400

            new_display = data['display']

            # Validate display settings
            int_fields = ['line_height', 'header_line_height', 'header_rows', 'font_shift']
            float_fields = ['interval']

            for field in int_fields:
                if field in new_display:
                    try:
                        value = int(new_display[field])
                        if value <= 0:
                            return jsonify({'error': f'{field} must be a positive integer'}), 400
                        new_display[field] = value
                    except (ValueError, TypeError):
                        return jsonify({'error': f'{field} must be an integer'}), 400

            for field in float_fields:
                if field in new_display:
                    try:
                        value = float(new_display[field])
                        if value <= 0:
                            return jsonify({'error': f'{field} must be a positive number'}), 400
                        new_display[field] = value
                    except (ValueError, TypeError):
                        return jsonify({'error': f'{field} must be a number'}), 400

            # Load current settings
            settings_file = self.config_dir / "settings.toml"
            with open(settings_file, 'r', encoding='utf-8') as f:
                config = toml.load(f)

            # Update display section
            if 'display' not in config:
                config['display'] = {}
            config['display'].update(new_display)

            # Write back to file
            with open(settings_file, 'w', encoding='utf-8') as f:
                toml.dump(config, f)

            logging.info(f"Updated display settings: {new_display}")
            return jsonify({'success': True, 'display': config['display']}), 200

        except FileNotFoundError:
            return jsonify({'error': 'settings.toml file not found'}), 404
        except Exception as e:
            logging.error(f"Error setting display settings: {e}")
            return jsonify({'error': str(e)}), 500

    def start(self):
        """Start the web server in a background thread."""
        if self.server_thread is not None and self.server_thread.is_alive():
            logging.warning("Web server already running")
            return

        def run_server():
            logging.info(f"Starting web server on http://{self.host}:{self.port}")
            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logging.info(f"Web interface available at http://{self.host}:{self.port}")

    def stop(self):
        """Stop the web server (not fully implemented - Flask doesn't support graceful shutdown easily)."""
        logging.info("Web server stopping (note: Flask server will continue until main process exits)")


def start_web_server(config_dir: str, host: str = "0.0.0.0", port: int = 5000) -> Optional[WebServer]:
    """Start the web server.

    Args:
        config_dir: Path to configuration directory
        host: Host to bind to
        port: Port to listen on

    Returns:
        WebServer instance if started successfully, None otherwise
    """
    try:
        server = WebServer(config_dir, host, port)
        server.start()
        return server
    except Exception as e:
        logging.error(f"Failed to start web server: {e}")
        return None
