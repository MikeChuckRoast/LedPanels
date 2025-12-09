#!/usr/bin/env python3
"""
Fetch team badge colors from athletic.net team page.

Usage:
    python fetch_team_colors.py <team_id>

Example:
    python fetch_team_colors.py 12345

Requirements:
    pip install selenium beautifulsoup4
"""

import re
import sys
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def rgb_to_hex(rgb_string):
    """
    Convert RGB color string to hex format.

    Args:
        rgb_string: String like "rgb(255, 238, 68)" or "rgb(16, 136, 16)"

    Returns:
        Hex color string like "#ffee44" or "#108810"
    """
    # Extract numbers from rgb string
    match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', rgb_string)
    if not match:
        return None

    r, g, b = map(int, match.groups())
    return f"#{r:02x}{g:02x}{b:02x}"


def fetch_team_colors(team_id, debug=False):
    """
    Fetch badge colors from athletic.net team page.

    Args:
        team_id: The team ID number
        debug: If True, print diagnostic information

    Returns:
        Comma-separated hex color codes (e.g., "#ffee44,#108810")
    """
    url = f"https://www.athletic.net/team/{team_id}"

    # Set up Chrome options for headless browsing
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

    driver = None
    try:
        if debug:
            print(f"\n=== DEBUG MODE ===", file=sys.stderr)
            print(f"URL: {url}", file=sys.stderr)
            print("Initializing browser...", file=sys.stderr)

        driver = webdriver.Chrome(options=chrome_options)
        driver.get(url)

        if debug:
            print("Page loaded, waiting for content...", file=sys.stderr)

        # Wait for badge elements to appear (max 10 seconds)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "badge-sport"))
            )
            if debug:
                print("Badge elements found!", file=sys.stderr)
        except:
            if debug:
                print("Timeout waiting for badge-sport elements, proceeding anyway...", file=sys.stderr)
            # Give it a bit more time
            time.sleep(2)

        # Get the page source after JavaScript has rendered
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')

        if debug:
            # Find all span elements with class "badge"
            all_badges = soup.find_all('span', class_='badge')
            print(f"\nFound {len(all_badges)} span elements with class 'badge'", file=sys.stderr)

            for i, badge in enumerate(all_badges[:10]):  # Show first 10
                print(f"\nBadge {i+1}:", file=sys.stderr)
                print(f"  Classes: {badge.get('class', [])}", file=sys.stderr)
                print(f"  Style: {badge.get('style', 'None')}", file=sys.stderr)
                print(f"  Text: {badge.get_text(strip=True)}", file=sys.stderr)

            # Also look for badge-sport specifically
            badge_sport = soup.find_all('span', class_='badge-sport')
            print(f"\nFound {len(badge_sport)} span elements with class 'badge-sport'", file=sys.stderr)

            for i, badge in enumerate(badge_sport[:10]):
                print(f"\nBadge-sport {i+1}:", file=sys.stderr)
                print(f"  Classes: {badge.get('class', [])}", file=sys.stderr)
                print(f"  Style: {badge.get('style', 'None')}", file=sys.stderr)
                print(f"  Text: {badge.get_text(strip=True)}", file=sys.stderr)

            print(f"\n=================\n", file=sys.stderr)

        # Find all span elements with class "badge-sport"
        badges = soup.find_all('span', class_='badge-sport')

        colors = []
        for badge in badges:
            style = badge.get('style', '')
            if 'background-color' in style:
                # Extract the background-color value
                match = re.search(r'background-color:\s*([^;]+)', style)
                if match:
                    color_value = match.group(1).strip()
                    hex_color = rgb_to_hex(color_value)
                    if hex_color:
                        colors.append(hex_color)

        if not colors:
            print("No badge colors found on page", file=sys.stderr)
            if not debug:
                print("Run with --debug flag for more information", file=sys.stderr)
            return None

        return ','.join(colors)

    except Exception as e:
        print(f"Error fetching page: {e}", file=sys.stderr)
        if debug:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return None
    finally:
        if driver:
            driver.quit()


def main():
    debug = '--debug' in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != '--debug']

    if len(args) != 1:
        print("Usage: python fetch_team_colors.py <team_id> [--debug]", file=sys.stderr)
        sys.exit(1)

    try:
        team_id = int(args[0])
    except ValueError:
        print("Error: team_id must be a number", file=sys.stderr)
        sys.exit(1)

    colors = fetch_team_colors(team_id, debug=debug)
    if colors:
        print(colors)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
