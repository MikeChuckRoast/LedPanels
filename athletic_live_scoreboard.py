"""
athletic_live_scoreboard.py

Polls an AthleticLIVE field event scoreboard (sb.athletic.live) and displays
the current athlete name, team, attempt number, and distance on the LED panel.

Usage:
    python athletic_live_scoreboard.py --name FUSHIABOX --uuid dc4113ed-50f3-424d-ae9c-02f0745d7285

The --name and --uuid values come from the scoreboard URL:
    https://sb.athletic.live/$web/boards/src/scoreboards/fieldResult/index.html
        ?name=FUSHIABOX&uuid=dc4113ed-50f3-424d-ae9c-02f0745d7285&...

How it works:
    1. Fetches board config from fieldappapi.athletic.live to get meetId + eventId.
    2. Polls the Firebase Realtime Database (trackmeet-io project) every --interval
       seconds for the most recent field result (lastMark + upNow).
    3. Renders up to 3 lines of text on the LED panel:
         Line 1: event name  (e.g. "Boys Shot Put")
         Line 2: athlete + attempt  (e.g. "N. Battle  #3")
         Line 3: distance  (e.g. "27-01.00")
    For a panel with more height, all 4 pieces are shown individually.

Dependencies:
    pip install requests
    (rgbmatrix or RGBMatrixEmulator must already be installed)
"""

import argparse
import logging
import os
import sys
import time
from typing import Optional

import requests

from display_utils import (calculate_text_baseline, fill_rectangle,
                           load_font_metadata, load_font_with_fallback,
                           measure_text_width, truncate_text_to_width)
from event_parser import load_affiliation_colors, resolve_affiliation_colors
from matrix_backend import get_matrix_backend

# ---------------------------------------------------------------------------
# AthleticLIVE API constants (discovered by reverse-engineering sb.athletic.live)
# ---------------------------------------------------------------------------
BOARD_CONFIG_URL = (
    "https://fieldappapi.athletic.live/athletic-sb/computer-config-board-file"
    "?name={name}&uuid={uuid}"
)
FIREBASE_BASE = "https://trackmeet-io.firebaseio.com"
FIREBASE_BOARD_PATH = "/athletic_sb/{uuid}-{name}.json"
FIREBASE_FIELD_PATH = "/meet_{meet_id}/liveFieldResults/{event_id}.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_board_config(name: str, uuid: str) -> dict:
    """Fetch the scoreboard configuration from the AthleticLIVE board API."""
    url = BOARD_CONFIG_URL.format(name=name, uuid=uuid)
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def fetch_board_state(name: str, uuid: str) -> Optional[dict]:
    """Fetch the live board state from Firebase RTDB (contains meetId)."""
    url = FIREBASE_BASE + FIREBASE_BOARD_PATH.format(uuid=uuid, name=name)
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def fetch_live_field_data(meet_id: int, event_id: str) -> Optional[dict]:
    """Poll the Firebase RTDB for the current field event results."""
    url = FIREBASE_BASE + FIREBASE_FIELD_PATH.format(
        meet_id=meet_id, event_id=event_id
    )
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()  # may be None if no data yet


# ---------------------------------------------------------------------------
# Data parsing  (Firebase stores abbreviated keys; we map them manually)
# ---------------------------------------------------------------------------

def _first_competition_area(data: dict) -> Optional[dict]:
    """Return the first competitionArea entry (abbreviated key: 'ca')."""
    if not data or "ca" not in data:
        return None
    areas = data["ca"]
    if not areas:
        return None
    # Take the first area (e.g. "sb1" for Flight 1)
    key = next(iter(areas))
    return areas[key]


def parse_scoreboard_text(raw: Optional[dict], fallback_event_name: str) -> dict:
    """Normalize Firebase field-result payload for rendering."""
    result = {
        "event_name": fallback_event_name,
        "place": "",
        "first_name": "",
        "last_initial": "",
        "team_name": "",
        "attempt": "",
        "mark": "",
        "latest_attempt_mark": "",
        "marks": [],
        "best_mark": "",
        "all_foul": False,
    }

    area = _first_competition_area(raw)
    if not area:
        log.debug("No competition area found in raw data: %s", raw)
        return result

    # `un` is typically provided under `v.un` in liveFieldResults payloads.
    event_un = ""
    if isinstance(raw, dict):
        event_un = ((raw.get("v") or {}).get("un") or "").strip()
    if not event_un:
        # Keep compatibility with payload variants where `un` may appear on area.
        event_un = (area.get("un") or "").strip()
    result["event_name"] = event_un or (fallback_event_name or "").strip()

    last_mark = area.get("lm") or {}
    up_now = area.get("up") or {}

    selected_athlete = {}
    selected_mark = {}
    if last_mark.get("m", {}).get("m"):
        selected_athlete = last_mark.get("a", {}) or {}
        selected_mark = last_mark.get("m", {}) or {}
    elif up_now:
        selected_athlete = up_now
        selected_mark = {"att": up_now.get("att", ""), "m": "(standing)"}

    first_name = (selected_athlete.get("fn") or "").strip()
    last_name = (selected_athlete.get("l") or "").strip()
    full_name = (selected_athlete.get("n") or "").strip()

    if not first_name and full_name:
        parts = full_name.split()
        if parts:
            first_name = parts[0]
            if len(parts) > 1 and not last_name:
                last_name = parts[-1]

    result["first_name"] = first_name
    result["last_initial"] = (last_name[:1].upper() if last_name else "")
    result["team_name"] = (selected_athlete.get("tn") or "").strip()

    place_val = selected_athlete.get("p", "")
    result["place"] = str(place_val).strip() if place_val != "" else ""

    result["attempt"] = str(selected_mark.get("att", "")).strip()
    result["mark"] = str(selected_mark.get("m", "")).strip()
    if result["attempt"] or result["mark"]:
        result["latest_attempt_mark"] = (f"#{result['attempt']} {result['mark']}").strip()

    # Horizontal event marks are provided in `fs`; keep the most recent values.
    all_marks = []
    best_mark_value = None
    best_mark_text = ""

    for item in (last_mark.get("fs") or []):
        att = str(item.get("att", "")).strip()
        mark = str(item.get("m", "")).strip()
        if att or mark:
            all_marks.append(f"#{att} {mark}".strip())
            # Extract numeric value for best-mark comparison (skip FOUL)
            if mark and "FOUL" not in mark.upper():
                try:
                    # For measurements like "9-07.75", extract the decimal equivalent
                    if "-" in mark:
                        parts = mark.split("-")
                        feet = float(parts[0])
                        inches = float(parts[1]) if len(parts) > 1 else 0
                        val = feet + inches / 12.0
                    else:
                        val = float(mark.replace("(standing)", "0"))
                    if best_mark_value is None or val > best_mark_value:
                        best_mark_value = val
                        best_mark_text = mark
                except (ValueError, IndexError):
                    pass

    # Exclude the current/latest mark from additional marks list.
    latest_key = result["latest_attempt_mark"].strip()
    if latest_key:
        all_marks = [m for m in all_marks if m.strip() != latest_key]

    result["marks"] = all_marks
    result["best_mark"] = best_mark_text
    result["all_foul"] = (len(all_marks) > 0 and all("FOUL" in m.upper() for m in all_marks))
    if not best_mark_text and all_marks:
        result["all_foul"] = True
    return result


# ---------------------------------------------------------------------------
# LED rendering
# ---------------------------------------------------------------------------

def render_on_matrix(
    matrix,
    graphics,
    font,
    font_metadata: dict,
    font_best,
    font_best_metadata: dict,
    data: dict,
    team_colors: dict,
    panel_width: int,
    panel_height: int,
):
    """Render a fixed 128x128 scoreboard layout."""
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()

    # Fixed block layout
    # 0..23   : Event name row (24)
    # 24..55  : Place + athlete row (32)
    # 56..79  : Latest attempt/mark row (24)
    # 80..127 : Marks grid area (48)
    header_y = 0
    header_h = 24
    athlete_y = 24
    athlete_h = 32
    latest_y = 56
    latest_h = 24
    grid_y = 80
    grid_h = 48

    white = graphics.Color(255, 255, 255)
    black = graphics.Color(0, 0, 0)

    # Resolve team colors using shared helper (same color source as display_event)
    team_name = (data.get("team_name") or "").strip()
    bg_rgb, fg_rgb, _ = resolve_affiliation_colors(team_name, team_colors)
    team_bg = graphics.Color(bg_rgb[0], bg_rgb[1], bg_rgb[2])
    team_fg = graphics.Color(fg_rgb[0], fg_rgb[1], fg_rgb[2])

    # Header: black background, centered white text
    fill_rectangle(canvas, graphics, 0, header_y, panel_width - 1, header_y + header_h - 1, black)
    header_text = truncate_text_to_width(font, data.get("event_name", ""), panel_width - 4)
    header_w = measure_text_width(font, header_text)
    header_x = max(0, (panel_width - header_w) // 2)
    header_baseline = calculate_text_baseline(header_y, header_h, font_metadata, 0)
    graphics.DrawText(canvas, font, header_x, header_baseline, white, header_text)

    # Middle row backgrounds use team colors
    place_box_w = 32
    athlete_box_w = panel_width - place_box_w
    fill_rectangle(canvas, graphics, 0, athlete_y, place_box_w - 1, athlete_y + athlete_h - 1, team_bg)
    fill_rectangle(canvas, graphics, place_box_w, athlete_y, panel_width - 1, athlete_y + athlete_h - 1, team_bg)

    # Place box text (centered)
    place_text = str(data.get("place") or "")
    place_text = truncate_text_to_width(font_best, place_text, place_box_w - 4)
    place_w = measure_text_width(font_best, place_text)
    place_x = max(0, (place_box_w - place_w) // 2)
    place_baseline = calculate_text_baseline(athlete_y, athlete_h, font_best_metadata, 0)
    graphics.DrawText(canvas, font_best, place_x, place_baseline, team_fg, place_text)

    # Athlete name + team in the 96x32 area (two centered 16px lines)
    name_line_h = 16
    team_line_h = 16
    first_name = (data.get("first_name") or "").strip()
    last_initial = (data.get("last_initial") or "").strip()
    athlete_name = (f"{first_name} {last_initial}".strip() if first_name else "")

    athlete_name = truncate_text_to_width(font, athlete_name, athlete_box_w - 4)
    athlete_name_w = measure_text_width(font, athlete_name)
    athlete_name_x = place_box_w + max(0, (athlete_box_w - athlete_name_w) // 2)
    athlete_name_baseline = calculate_text_baseline(athlete_y, name_line_h, font_metadata, 0)
    graphics.DrawText(canvas, font, athlete_name_x, athlete_name_baseline, team_fg, athlete_name)

    team_text = truncate_text_to_width(font, team_name, athlete_box_w - 4)
    team_w = measure_text_width(font, team_text)
    team_x = place_box_w + max(0, (athlete_box_w - team_w) // 2)
    team_baseline = calculate_text_baseline(athlete_y + name_line_h, team_line_h, font_metadata, 0)
    graphics.DrawText(canvas, font, team_x, team_baseline, team_fg, team_text)

    # Latest attempt + mark: white background, centered black text
    fill_rectangle(canvas, graphics, 0, latest_y, panel_width - 1, latest_y + latest_h - 1, white)
    latest_text = truncate_text_to_width(font, data.get("latest_attempt_mark", ""), panel_width - 4)
    latest_w = measure_text_width(font, latest_text)
    latest_x = max(0, (panel_width - latest_w) // 2)
    latest_baseline = calculate_text_baseline(latest_y, latest_h, font_metadata, 0)
    graphics.DrawText(canvas, font, latest_x, latest_baseline, black, latest_text)

    # Best mark display area: black background for label, green for best value
    label_h = 16
    value_h = grid_h - label_h

    fill_rectangle(canvas, graphics, 0, grid_y, panel_width - 1, grid_y + label_h - 1, black)

    # Draw "Best" label (white on black)
    label_text = "Best"
    label_w = measure_text_width(font, label_text)
    label_x = max(0, (panel_width - label_w) // 2)
    label_baseline = calculate_text_baseline(grid_y, label_h, font_metadata, 0)
    graphics.DrawText(canvas, font, label_x, label_baseline, white, label_text)

    # Draw best mark value or FOUL message
    if data.get("all_foul"):
        # All marks are fouls: red background with white "FOUL" text
        red = graphics.Color(255, 0, 0)
        fill_rectangle(canvas, graphics, 0, grid_y + label_h, panel_width - 1, grid_y + grid_h - 1, red)
        foul_text = "FOUL"
        foul_w = measure_text_width(font_best, foul_text)
        foul_x = max(0, (panel_width - foul_w) // 2)
        foul_baseline = calculate_text_baseline(grid_y + label_h, value_h, font_best_metadata, 0)
        graphics.DrawText(canvas, font_best, foul_x, foul_baseline, white, foul_text)
    else:
        # Green background with best mark value
        green = graphics.Color(0, 255, 0)
        fill_rectangle(canvas, graphics, 0, grid_y + label_h, panel_width - 1, grid_y + grid_h - 1, green)
        best_text = truncate_text_to_width(font_best, data.get("best_mark", ""), panel_width - 4)
        best_w = measure_text_width(font_best, best_text)
        best_x = max(0, (panel_width - best_w) // 2)
        best_baseline = calculate_text_baseline(grid_y + label_h, value_h, font_best_metadata, 0)
        graphics.DrawText(canvas, font_best, best_x, best_baseline, white, best_text)

    matrix.SwapOnVSync(canvas)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Display an AthleticLIVE field scoreboard on an LED panel."
    )
    parser.add_argument(
        "--name", required=True,
        help="Scoreboard computer name from the URL (e.g. FUSHIABOX)"
    )
    parser.add_argument(
        "--uuid", required=True,
        help="Scoreboard UUID from the URL"
    )
    parser.add_argument(
        "--interval", type=float, default=3.0,
        help="Poll interval in seconds (default: 3)"
    )
    parser.add_argument(
        "--rows",    type=int, default=32,  help="LED panel rows (default: 32)"
    )
    parser.add_argument(
        "--cols",    type=int, default=64,  help="LED panel cols (default: 64)"
    )
    parser.add_argument(
        "--chain",   type=int, default=2,   help="Chain length (default: 2)"
    )
    parser.add_argument(
        "--parallel",type=int, default=4,   help="Parallel chains (default: 4)"
    )
    parser.add_argument(
        "--gpio-slowdown", type=int, default=3, help="GPIO slowdown (default: 3)"
    )
    parser.add_argument(
        "--fpp", action="store_true", default=False,
        help="Use FPP output instead of direct matrix control"
    )
    parser.add_argument(
        "--fpp-host", default="127.0.0.1",
        help="FPP host IP address"
    )
    parser.add_argument(
        "--fpp-port", type=int, default=4048,
        help="FPP DDP port"
    )
    parser.add_argument(
        "--colorlight", action="store_true", default=False,
        help="Send frames to ColorLight 5A-75B via raw Ethernet (requires root/sudo)"
    )
    parser.add_argument(
        "--colorlight-interface", default="eth0",
        help="Network interface for ColorLight (e.g., eth0)"
    )
    parser.add_argument(
        "--font",
        default="fonts/helvB14.bdf",
        help="BDF font path (default: fonts/helvB14.bdf)"
    )
    parser.add_argument(
        "--colors-csv",
        default=os.path.join("config", "colors.csv"),
        help="Path to colors CSV (default: config/colors.csv)"
    )
    args = parser.parse_args()

    # -- Fetch board config once ------------------------------------------
    log.info("Fetching board config for %s / %s …", args.name, args.uuid)
    try:
        config = fetch_board_config(args.name, args.uuid)
    except Exception as exc:
        log.error("Failed to fetch board config: %s", exc)
        sys.exit(1)

    event_id   = config.get("documentId")
    event_name = config.get("documentValue", "")

    if not event_id:
        log.error("Board config did not contain documentId. Got: %s", config)
        sys.exit(1)

    # meetId lives in the Firebase board state, not the config file
    log.info("Fetching board state from Firebase …")
    try:
        board_state = fetch_board_state(args.name, args.uuid)
    except Exception as exc:
        log.error("Failed to fetch Firebase board state: %s", exc)
        sys.exit(1)

    if not board_state or "meetId" not in board_state:
        log.error("Firebase board state did not contain meetId. Got: %s", board_state)
        sys.exit(1)

    meet_id = board_state["meetId"]

    log.info("Meet ID: %s  Event ID: %s  Event: %s", meet_id, event_id, event_name)

    team_colors = load_affiliation_colors(args.colors_csv)

    # -- Set up LED matrix ------------------------------------------------
    RGBMatrix, RGBMatrixOptions, graphics = get_matrix_backend(
        use_fpp=args.fpp,
        fpp_host=args.fpp_host,
        fpp_port=args.fpp_port,
        use_colorlight=args.colorlight,
        colorlight_interface=args.colorlight_interface,
        width=args.cols,
        height=args.rows,
    )

    options = RGBMatrixOptions()
    options.rows         = args.rows
    options.cols         = args.cols
    options.chain_length = args.chain
    options.parallel     = args.parallel
    options.gpio_slowdown = args.gpio_slowdown

    matrix = RGBMatrix(options=options)

    font = load_font_with_fallback(graphics, args.font)
    try:
        font_metadata = load_font_metadata(args.font)
    except Exception:
        # Safe fallback when metadata parsing fails.
        font_metadata = {"cap_height": 10, "font_ascent": 10}
        log.warning("Could not load font metadata for %s; using fallback metrics.", args.font)

    font_best = load_font_with_fallback(graphics, "fonts/helvB18.bdf")
    try:
        font_best_metadata = load_font_metadata("fonts/helvB18.bdf")
    except Exception:
        # Safe fallback when metadata parsing fails.
        font_best_metadata = {"cap_height": 14, "font_ascent": 14}
        log.warning("Could not load font metadata for helvB18.bdf; using fallback metrics.")

    panel_width  = args.cols * args.chain
    panel_height = args.rows * args.parallel

    if panel_width != 128 or panel_height != 128:
        log.warning(
            "Layout is designed for 128x128; current canvas is %sx%s and may clip.",
            panel_width,
            panel_height,
        )

    # -- Poll loop --------------------------------------------------------
    last_data = None
    last_board_check = 0
    log.info("Polling Firebase every %.1fs …  (Ctrl-C to stop)", args.interval)

    try:
        while True:
            try:
                # Every 30 seconds, re-check the board state to detect event changes
                now = time.time()
                if now - last_board_check > 30:
                    log.debug("Re-checking board state for event changes...")
                    try:
                        new_board_state = fetch_board_state(args.name, args.uuid)
                        new_event_id = new_board_state.get("documentId")

                        if new_event_id and new_event_id != event_id:
                            log.info("Event changed: %s to %s, re-fetching config…", event_id, new_event_id)
                            # Re-fetch config to get the new event name (documentValue)
                            config = fetch_board_config(args.name, args.uuid)
                            new_event_name = config.get("documentValue", "")

                            log.info("Event changed: %s (%s) → %s (%s)",
                                     event_id, event_name, new_event_id, new_event_name)
                            event_id = new_event_id
                            event_name = new_event_name
                            last_data = None  # Force a re-render with new event
                    except Exception as exc:
                        log.warning("Could not re-check board state: %s", exc)

                    last_board_check = now

                log.debug("Fetching live field data for meet_id=%s event_id=%s", meet_id, event_id)
                raw = fetch_live_field_data(meet_id, event_id)
                log.debug("Raw Firebase response: %s", raw)
                data = parse_scoreboard_text(raw, event_name)
                log.debug("Parsed data: %s", data)

                # Only re-render when something changed
                if data != last_data:
                    log.info(
                        "%s | place %s | %s %s (%s) | %s",
                        data["event_name"],
                        data["place"],
                        data["first_name"],
                        data["last_initial"],
                        data["team_name"],
                        data["latest_attempt_mark"],
                    )
                    render_on_matrix(
                        matrix,
                        graphics,
                        font,
                        font_metadata,
                        font_best,
                        font_best_metadata,
                        data,
                        team_colors,
                        panel_width,
                        panel_height,
                    )
                    last_data = data
                else:
                    log.debug("Data unchanged, skipping render")

            except requests.RequestException as exc:
                log.warning("Network error: %s", exc)
            except Exception as exc:
                log.exception("Unexpected error: %s", exc)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
