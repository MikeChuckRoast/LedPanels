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
    result["last_name"] = last_name
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
# Formatting helpers
# ---------------------------------------------------------------------------

def _ordinal_place(place_str: str) -> str:
    """Convert a place number string to ordinal form, e.g. '15' -> '15th Place'."""
    try:
        n = int(place_str)
    except (ValueError, TypeError):
        return place_str
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix} Place"


def _format_mark(mark_str: str) -> str:
    """Format a field-event mark from '18-05.75' to \"18' 5.75\"\"."""
    mark_str = mark_str.strip()
    if not mark_str or mark_str.upper() in ("(STANDING)", "FOUL"):
        return mark_str
    if "-" in mark_str:
        parts = mark_str.split("-", 1)
        try:
            feet = int(parts[0])
            inches_val = float(parts[1])
            if inches_val == int(inches_val):
                inches_str = str(int(inches_val))
            else:
                inches_str = f"{inches_val:.2f}".rstrip("0")
            return f"{feet}' {inches_str}\""
        except (ValueError, IndexError):
            pass
    return mark_str


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

    # Fixed block layout (total = 128px)
    # 0..19   : Event name (20px)  — white bg, black text, centered
    # 20..43  : Athlete name (24px) — affiliation colors, centered
    # 44..67  : Team name (24px)   — affiliation colors, centered
    # 68..87  : Place (20px)       — black bg, white text, centered
    # 88..107 : Last mark (20px)   — black bg, "Last:" left / mark right
    # 108..127: Best mark (20px)   — black bg, "Best:" left / mark right
    event_y = 0;   event_h = 20
    name_y  = 20;  name_h  = 24
    team_y  = 44;  team_h  = 24
    place_y = 68;  place_h = 20
    last_y  = 88;  last_h  = 20
    best_y  = 108; best_h  = 20

    white = graphics.Color(255, 255, 255)
    black = graphics.Color(0, 0, 0)

    # Resolve team colors using shared helper (same color source as display_event)
    team_name = (data.get("team_name") or "").strip()
    bg_rgb, fg_rgb, _ = resolve_affiliation_colors(team_name, team_colors)
    team_bg = graphics.Color(bg_rgb[0], bg_rgb[1], bg_rgb[2])
    team_fg = graphics.Color(fg_rgb[0], fg_rgb[1], fg_rgb[2])

    # Row 1: Event name — white background, black text, centered
    fill_rectangle(canvas, graphics, 0, event_y, panel_width - 1, event_y + event_h - 1, white)
    event_text = truncate_text_to_width(font, data.get("event_name", ""), panel_width - 4)
    event_w = measure_text_width(font, event_text)
    event_x = max(0, (panel_width - event_w) // 2)
    event_baseline = calculate_text_baseline(event_y, event_h, font_metadata, 0)
    graphics.DrawText(canvas, font, event_x, event_baseline, black, event_text)

    # Row 2: Athlete full name — affiliation colors, centered
    fill_rectangle(canvas, graphics, 0, name_y, panel_width - 1, name_y + name_h - 1, team_bg)
    first_name = (data.get("first_name") or "").strip()
    last_name  = (data.get("last_name") or "").strip()
    athlete_name = f"{first_name} {last_name}".strip() if first_name else ""
    athlete_name = truncate_text_to_width(font, athlete_name, panel_width - 4)
    athlete_w = measure_text_width(font, athlete_name)
    athlete_x = max(0, (panel_width - athlete_w) // 2)
    athlete_baseline = calculate_text_baseline(name_y, name_h, font_metadata, 0)
    graphics.DrawText(canvas, font, athlete_x, athlete_baseline, team_fg, athlete_name)

    # Row 3: Team name — affiliation colors, centered
    fill_rectangle(canvas, graphics, 0, team_y, panel_width - 1, team_y + team_h - 1, team_bg)
    team_text = truncate_text_to_width(font, team_name, panel_width - 4)
    team_w = measure_text_width(font, team_text)
    team_x = max(0, (panel_width - team_w) // 2)
    team_baseline = calculate_text_baseline(team_y, team_h, font_metadata, 0)
    graphics.DrawText(canvas, font, team_x, team_baseline, team_fg, team_text)

    # Row 4: Place — black background, white text, centered ("15th Place")
    fill_rectangle(canvas, graphics, 0, place_y, panel_width - 1, place_y + place_h - 1, black)
    place_raw = str(data.get("place") or "")
    place_text = _ordinal_place(place_raw) if place_raw else ""
    place_text = truncate_text_to_width(font, place_text, panel_width - 4)
    place_w = measure_text_width(font, place_text)
    place_x = max(0, (panel_width - place_w) // 2)
    place_baseline = calculate_text_baseline(place_y, place_h, font_metadata, 0)
    graphics.DrawText(canvas, font, place_x, place_baseline, white, place_text)

    # Row 5: Last mark — black bg, "Last:" left-justified, mark right-justified
    fill_rectangle(canvas, graphics, 0, last_y, panel_width - 1, last_y + last_h - 1, black)
    last_label = "Last:"
    last_mark_raw = (data.get("mark") or "").strip()
    last_mark_text = _format_mark(last_mark_raw) if last_mark_raw else ""
    last_baseline = calculate_text_baseline(last_y, last_h, font_metadata, 0)
    graphics.DrawText(canvas, font, 2, last_baseline, white, last_label)
    if last_mark_text:
        last_mark_w = measure_text_width(font, last_mark_text)
        graphics.DrawText(canvas, font, panel_width - last_mark_w - 2, last_baseline, white, last_mark_text)

    # Row 6: Best mark — black bg, "Best:" left-justified, mark right-justified
    fill_rectangle(canvas, graphics, 0, best_y, panel_width - 1, best_y + best_h - 1, black)
    best_label = "Best:"
    best_mark_raw = (data.get("best_mark") or "").strip()
    best_mark_text = _format_mark(best_mark_raw) if best_mark_raw else ""
    best_baseline = calculate_text_baseline(best_y, best_h, font_metadata, 0)
    graphics.DrawText(canvas, font, 2, best_baseline, white, best_label)
    if best_mark_text:
        best_mark_w = measure_text_width(font, best_mark_text)
        graphics.DrawText(canvas, font, panel_width - best_mark_w - 2, best_baseline, white, best_mark_text)

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
