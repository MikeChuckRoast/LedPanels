# Web Interface Guide

## Overview

The LED Display Control Panel provides a web-based interface for managing the display remotely from any browser on the network.

## Features

### 1. Status Page (Main Page)
- View all available events from `lynx.evt`
- See current event/round/heat selection
- Click any event to change the active display
- Changes take effect immediately (triggers file reload)

### 2. Team Settings Page
- Edit team color configurations
- Add/delete teams
- Color pickers for background and text colors
- Live preview of team colors
- Validates color formats before saving

### 3. Display Settings Page
- Adjust display layout parameters:
  - Line Height (athlete row height)
  - Header Line Height (header row height)
  - Header Rows (text wrapping)
  - Page Interval (seconds per page)
  - Font Shift (vertical positioning)
- Changes take effect on next event reload

## Configuration

Edit `config/settings.toml`:

```toml
[web]
web_enabled = true           # Enable/disable web interface
web_host = "0.0.0.0"          # Host (0.0.0.0 = all interfaces, 127.0.0.1 = localhost only)
web_port = 5000              # Port for web server
```

## Usage

### Starting the Display with Web Interface

```bash
python display_event.py
```

The web server starts automatically if `web_enabled = true` in settings.

### Accessing the Interface

1. Find your Raspberry Pi's IP address:
   ```bash
   hostname -I
   ```

2. Open a browser on any device on the same network:
   ```
   http://<raspberry-pi-ip>:5000
   ```
   
   Example: `http://192.168.1.100:5000`

3. On the Pi itself:
   ```
   http://localhost:5000
   ```

## How It Works

### File-Based Communication

The web interface and display communicate through configuration files:

1. **Event Selection**: Web UI writes to `config/current_event.json`
2. **Team Colors**: Web UI writes to `config/colors.csv`
3. **Display Settings**: Web UI updates `config/settings.toml` [display] section
4. **File Monitor**: Detects changes and triggers reload automatically

### Data Flow

```
Browser → Web Server → Config Files → File Monitor → Display Reload
```

Changes typically take effect within 1-2 seconds.

## API Endpoints

The web server provides REST API endpoints:

### GET /api/events
Returns list of all events from `lynx.evt`

**Response:**
```json
{
  "events": [
    {
      "event": 1,
      "round": 1,
      "heat": 1,
      "name": "Boys 4x800 Relay Varsity",
      "athlete_count": 8
    }
  ]
}
```

### GET /api/current_event
Returns current event selection

**Response:**
```json
{
  "event": 1,
  "round": 1,
  "heat": 1
}
```

### POST /api/current_event
Update current event selection

**Request:**
```json
{
  "event": 1,
  "round": 1,
  "heat": 2
}
```

### GET /api/teams
Returns team color configurations

**Response:**
```json
{
  "teams": [
    {
      "affiliation": "Monroe Jefferson",
      "name": "Jefferson",
      "bgcolor": "#00aa00",
      "text": "#ffff00"
    }
  ]
}
```

### POST /api/teams
Update team colors

**Request:**
```json
{
  "teams": [
    {
      "affiliation": "Monroe Jefferson",
      "name": "Jefferson",
      "bgcolor": "#00aa00",
      "text": "#ffff00"
    }
  ]
}
```

### GET /api/display_settings
Returns display configuration

**Response:**
```json
{
  "display": {
    "line_height": 24,
    "header_line_height": 16,
    "header_rows": 2,
    "interval": 2.0,
    "font_shift": 7
  }
}
```

### POST /api/display_settings
Update display settings

**Request:**
```json
{
  "display": {
    "line_height": 24,
    "header_line_height": 16,
    "header_rows": 2,
    "interval": 2.0,
    "font_shift": 7
  }
}
```

## Troubleshooting

### Web interface not accessible

1. Check web server is enabled:
   ```bash
   grep web_enabled config/settings.toml
   ```

2. Check display_event.py logs for "Web interface available" message

3. Verify firewall allows port 5000:
   ```bash
   sudo ufw allow 5000
   ```

4. Test locally first:
   ```bash
   curl http://localhost:5000/api/events
   ```

### Changes not taking effect

1. Check file monitoring is enabled:
   ```bash
   grep file_watch_enabled config/settings.toml
   ```

2. Look for "File change detected" in display logs

3. Verify files are being written (check timestamps):
   ```bash
   ls -l config/current_event.json
   ```

### Port already in use

Change the port in `config/settings.toml`:
```toml
[web]
web_port = 5001  # Use different port
```

## Security Notes

- **No authentication**: The web interface has no password protection
- **Local network only**: Only accessible from devices on same network (if using 0.0.0.0)
- **Localhost only**: Set `web_host = "127.0.0.1"` to restrict to Pi only
- **Firewall**: Consider using firewall rules to restrict access

## Mobile-Friendly

The web interface is responsive and works on:
- Desktop browsers (Chrome, Firefox, Safari, Edge)
- Tablets (iPad, Android tablets)
- Mobile phones (iPhone, Android phones)

## Browser Compatibility

- Modern browsers (2020+) required
- Uses vanilla JavaScript (no frameworks)
- CSS Grid and Flexbox for layout
- Tested on Chrome, Firefox, Safari, Edge
