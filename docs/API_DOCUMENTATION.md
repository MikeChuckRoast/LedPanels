# LED Display Web API Documentation

This document describes the HTTP API endpoints for controlling the LED display system. These APIs allow external applications to update event data, schedules, and current event selection.

## Base URL

All endpoints are relative to the web server base URL. By default, the server runs on `http://localhost:5000`, but this can be configured.

Example: `http://localhost:5000/api/current_event`

## Authentication

Currently, the API does not require authentication. Ensure the server is only accessible on trusted networks.

## Common Response Format

### Success Response
```json
{
  "success": true,
  ...additional fields...
}
```

### Error Response
```json
{
  "error": "Descriptive error message"
}
```

HTTP status codes:
- `200`: Success
- `400`: Client error (validation failure, malformed request)
- `404`: Resource not found
- `500`: Server error

---

## Event Selection API

### Set Current Event

Updates which event is currently displayed on the LED panels.

**Endpoint:** `POST /api/current_event`

**Request Body:**
```json
{
  "event": 1,
  "round": 1,
  "heat": 1
}
```

**Fields:**
- `event` (integer, required): Event number (must be positive)
- `round` (integer, required): Round number (must be positive)
- `heat` (integer, required): Heat number (must be positive)

**Success Response (200):**
```json
{
  "success": true,
  "current_event": {
    "event": 1,
    "round": 1,
    "heat": 1
  }
}
```

**Error Responses:**

Missing fields (400):
```json
{
  "error": "Missing required fields: event, round, heat"
}
```

Invalid values (400):
```json
{
  "error": "Event, round, and heat must be positive integers"
}
```

Invalid types (400):
```json
{
  "error": "Event, round, and heat must be integers"
}
```

**Example with cURL:**
```bash
curl -X POST http://localhost:5000/api/current_event \
  -H "Content-Type: application/json" \
  -d '{"event": 3, "round": 1, "heat": 2}'
```

**Example with Python:**
```python
import requests

url = "http://localhost:5000/api/current_event"
data = {
    "event": 3,
    "round": 1,
    "heat": 2
}

response = requests.post(url, json=data)
if response.status_code == 200:
    print("Success:", response.json())
else:
    print("Error:", response.json())
```

---

## File Upload APIs

These endpoints allow updating the event data (`lynx.evt`) and schedule (`lynx.sch`) files. When files are updated, automatic backups are created with `.bak` extension.

### Upload Events File

Replaces the `lynx.evt` file with new event and athlete data.

**Endpoint:** `POST /api/upload/events`

**Request Body:**
```json
{
  "content": "1,1,1,Boys 100m Dash Varsity,,,,,,100\n,1234,1,Smith,John,Lincoln,,,,,,,56789\n,1235,2,Doe,Jane,Jefferson,,,,,,,56790\n..."
}
```

**Fields:**
- `content` (string, required): Complete CSV content of the lynx.evt file

**lynx.evt File Format:**

The file contains event headers and athlete lines in CSV format.

**Event Header Line:**
```
event_num,round_num,heat_num,event_name,[unused],[unused],[unused],[unused],[unused],distance
```

Example:
```
2,1,1,Girls 4x800 Relay Varsity,,,,,,3200
```

**Athlete Line (Individual):**
```
,athlete_id,lane,last_name,first_name,affiliation,[unused],[unused],[unused],[unused],[unused],team_id
```

Example:
```
,1234,1,Smith,John,Lincoln,,,,,,,56789
```

**Athlete Line (Relay Team):**
```
,athlete_id,lane,team_name,,affiliation_code,[unused],[unused],[unused],[unused],[unused],team_id
```

Example (note empty first_name field and affiliation format):
```
,5678,1,Divine Child,,ddcm  A,,,,,,38076
```

**Important Notes:**
- Athlete lines start with a comma (empty first field)
- Event header lines start with the event number
- For relay events, the `first_name` field is empty and `last_name` contains the team name
- Relay affiliations follow pattern: 2-4 letter code + spaces + letter (e.g., "ddcm  A")

**Success Response (200):**
```json
{
  "success": true,
  "event_count": 45
}
```

**Error Responses:**

Missing content (400):
```json
{
  "error": "Missing or invalid content field (must be string)"
}
```

Empty content (400):
```json
{
  "error": "Content cannot be empty"
}
```

Invalid format (400):
```json
{
  "error": "Invalid lynx.evt format: [parse error details]"
}
```

No valid events (400):
```json
{
  "error": "No valid events found in content"
}
```

**Behavior:**
- Creates backup: `lynx.evt.bak` (overwrites previous backup)
- Validates file can be parsed before replacing
- Uses temporary file to avoid corruption
- File watcher will automatically reload data after update

**Example with Python:**
```python
import requests

url = "http://localhost:5000/api/upload/events"

# Read file content
with open("lynx.evt", "r", encoding="utf-8") as f:
    content = f.read()

data = {"content": content}

response = requests.post(url, json=data)
if response.status_code == 200:
    result = response.json()
    print(f"Success: {result['event_count']} events uploaded")
else:
    print(f"Error: {response.json()['error']}")
```

---

### Upload Schedule File

Replaces the `lynx.sch` file with new schedule order. Validates that all schedule entries reference existing events in `lynx.evt`.

**Endpoint:** `POST /api/upload/schedule`

**Request Body:**
```json
{
  "content": "; Competition Schedule\nevent,round,heat\n3,1,1\n1,1,1\n7,1,2\n..."
}
```

**Fields:**
- `content` (string, required): Complete CSV content of the lynx.sch file

**lynx.sch File Format:**

Simple CSV file defining competition order.

```
; Comments start with semicolon
; This line is ignored
event,round,heat
3,1,1
1,1,1
7,1,2
```

**Format Rules:**
- Lines starting with `;` are comments (optional)
- Empty lines are ignored
- Each data line: `event,round,heat`
- All values must be positive integers
- Order matters - defines the sequence of competition

**Success Response (200):**
```json
{
  "success": true,
  "total_entries": 42,
  "valid_entries": 40,
  "invalid_entries": 2
}
```

**Fields:**
- `total_entries`: Number of entries in uploaded schedule
- `valid_entries`: Number that match existing events
- `invalid_entries`: Number that don't match (logged as warnings)

**Error Responses:**

Missing content (400):
```json
{
  "error": "Missing or invalid content field (must be string)"
}
```

Empty content (400):
```json
{
  "error": "Content cannot be empty"
}
```

Invalid format (400):
```json
{
  "error": "Invalid lynx.sch format: [parse error details]"
}
```

No valid entries (400):
```json
{
  "error": "No valid schedule entries found in content"
}
```

No matching events (400):
```json
{
  "error": "No valid schedule entries (none match existing events)"
}
```

Cannot load events for validation (500):
```json
{
  "error": "Cannot validate schedule: failed to load lynx.evt: [details]"
}
```

**Behavior:**
- Creates backup: `lynx.sch.bak` (overwrites previous backup)
- Validates file can be parsed before replacing
- Cross-validates entries against `lynx.evt`
- Entries not found in `lynx.evt` are logged as warnings but don't fail the upload
- Uses temporary file to avoid corruption
- File watcher will automatically reload data after update

**Example with Python:**
```python
import requests

url = "http://localhost:5000/api/upload/schedule"

# Read file content
with open("lynx.sch", "r", encoding="utf-8") as f:
    content = f.read()

data = {"content": content}

response = requests.post(url, json=data)
if response.status_code == 200:
    result = response.json()
    print(f"Success: {result['valid_entries']}/{result['total_entries']} valid entries")
    if result['invalid_entries'] > 0:
        print(f"Warning: {result['invalid_entries']} entries don't match events")
else:
    print(f"Error: {response.json()['error']}")
```

---

### Upload Combined (Events + Schedule)

Atomically updates both `lynx.evt` and `lynx.sch` files. Both files are validated before either is written. If validation fails for either file, neither is updated.

**Endpoint:** `POST /api/upload/combined`

**Request Body:**
```json
{
  "events": "1,1,1,Boys 100m...\n,1234,1,Smith,John,...",
  "schedule": "; Schedule\nevent,round,heat\n1,1,1\n..."
}
```

**Fields:**
- `events` (string, required): Complete CSV content of lynx.evt file
- `schedule` (string, required): Complete CSV content of lynx.sch file

**Success Response (200):**
```json
{
  "success": true,
  "events": {
    "event_count": 45
  },
  "schedule": {
    "total_entries": 42,
    "valid_entries": 40,
    "invalid_entries": 2
  }
}
```

**Error Responses:**

Missing fields (400):
```json
{
  "error": "Missing or invalid events field (must be string)"
}
```
```json
{
  "error": "Missing or invalid schedule field (must be string)"
}
```

Empty content (400):
```json
{
  "error": "Events content cannot be empty"
}
```
```json
{
  "error": "Schedule content cannot be empty"
}
```

Invalid events format (400):
```json
{
  "error": "Invalid lynx.evt format: [details]"
}
```

Invalid schedule format (400):
```json
{
  "error": "Invalid lynx.sch format: [details]"
}
```

No valid data (400):
```json
{
  "error": "No valid events found in events content"
}
```
```json
{
  "error": "No valid schedule entries (none match events in lynx.evt)"
}
```

**Behavior:**
- **Atomic operation**: Both files are validated before either is updated
- If validation fails, neither file is changed
- Creates backups: `lynx.evt.bak` and `lynx.sch.bak`
- Schedule is validated against the new events data (not existing data)
- Uses temporary files to avoid corruption
- File watcher will automatically reload data after update

**Example with Python:**
```python
import requests

url = "http://localhost:5000/api/upload/combined"

# Read both files
with open("lynx.evt", "r", encoding="utf-8") as f:
    events_content = f.read()

with open("lynx.sch", "r", encoding="utf-8") as f:
    schedule_content = f.read()

data = {
    "events": events_content,
    "schedule": schedule_content
}

response = requests.post(url, json=data)
if response.status_code == 200:
    result = response.json()
    print(f"Success!")
    print(f"Events: {result['events']['event_count']}")
    print(f"Schedule: {result['schedule']['valid_entries']}/{result['schedule']['total_entries']} valid")
else:
    print(f"Error: {response.json()['error']}")
```

---

## Complete Integration Example

Here's a complete Python script that updates both files and sets the current event:

```python
#!/usr/bin/env python3
"""
Complete example: Upload events and schedule, then set current event.
"""
import requests
import sys

def upload_files(server_url, events_file, schedule_file):
    """Upload both event and schedule files."""
    
    # Read file contents
    with open(events_file, "r", encoding="utf-8") as f:
        events_content = f.read()
    
    with open(schedule_file, "r", encoding="utf-8") as f:
        schedule_content = f.read()
    
    # Upload using combined endpoint for atomic update
    url = f"{server_url}/api/upload/combined"
    data = {
        "events": events_content,
        "schedule": schedule_content
    }
    
    print("Uploading files...")
    response = requests.post(url, json=data)
    
    if response.status_code != 200:
        print(f"Error uploading files: {response.json()['error']}")
        return False
    
    result = response.json()
    print(f"✓ Uploaded {result['events']['event_count']} events")
    print(f"✓ Uploaded {result['schedule']['valid_entries']} schedule entries")
    
    return True

def set_current_event(server_url, event, round_num, heat):
    """Set the current event to display."""
    
    url = f"{server_url}/api/current_event"
    data = {
        "event": event,
        "round": round_num,
        "heat": heat
    }
    
    print(f"Setting current event to {event}/{round_num}/{heat}...")
    response = requests.post(url, json=data)
    
    if response.status_code != 200:
        print(f"Error setting current event: {response.json()['error']}")
        return False
    
    print("✓ Current event updated")
    return True

if __name__ == "__main__":
    SERVER_URL = "http://localhost:5000"
    
    # Upload files
    if not upload_files(SERVER_URL, "lynx.evt", "lynx.sch"):
        sys.exit(1)
    
    # Set current event to first event
    if not set_current_event(SERVER_URL, 1, 1, 1):
        sys.exit(1)
    
    print("\n✓ All updates completed successfully!")
```

---

## Error Handling Best Practices

When integrating with this API, follow these practices:

1. **Always check HTTP status codes** before parsing response JSON
2. **Handle validation errors** (400) by checking file format
3. **Parse error messages** - they contain specific details about what failed
4. **Validate files locally** before uploading if possible
5. **Use the combined endpoint** when updating both files to ensure consistency
6. **Monitor for invalid_entries** in schedule uploads - indicates schedule/event mismatch
7. **Implement retry logic** for network errors (connection refused, timeouts)
8. **Check backup files** (`.bak`) if you need to recover from a bad upload

---

## File Backup and Recovery

All file upload endpoints automatically create backups:

- `config/lynx.evt.bak` - Previous events file
- `config/lynx.sch.bak` - Previous schedule file

**Recovery:**
1. Stop the web server
2. Copy `.bak` files over the current files:
   ```bash
   cp config/lynx.evt.bak config/lynx.evt
   cp config/lynx.sch.bak config/lynx.sch
   ```
3. Restart the web server

**Note:** Each upload overwrites the previous backup, so only one level of backup is maintained.

---

## Testing

To test the API endpoints:

1. **Use the provided test script** (see `tools/upload_events.py`)
2. **Check server logs** for detailed error messages
3. **Verify backups** were created after successful uploads
4. **Test with sample files** from `tests/fixtures/` directory

---

## Network Configuration

By default, the web server binds to `0.0.0.0:5000` (accessible from any network interface). To restrict access:

1. Edit `settings.toml`
2. Change host to `127.0.0.1` (localhost only)
3. Use firewall rules to restrict access
4. Consider adding authentication for production use

---

## Support

For issues or questions:
- Check server logs for detailed error messages
- Verify file formats match specifications
- Test with sample files from `tests/fixtures/`
- Ensure `lynx.evt` exists before uploading `lynx.sch` (schedule validation requires events)
