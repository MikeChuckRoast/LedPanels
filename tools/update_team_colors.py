#!/usr/bin/env python3
"""
Update team colors CSV with missing teams from lynx.evt file.

This script:
1. Reads the lynx.evt file from the config directory
2. Extracts all unique team names (affiliations)
3. Compares them to colors.csv
4. Adds missing teams with default values (black background, white text)
"""

import csv
import os
import sys
from pathlib import Path


def get_project_root():
    """Get the project root directory (parent of tools directory)."""
    return Path(__file__).parent.parent


def parse_lynx_teams(lynx_path):
    """Parse lynx.evt file and extract unique team affiliations.

    Args:
        lynx_path: Path to lynx.evt file

    Returns:
        Set of unique team affiliation names
    """
    teams = set()

    if not os.path.isfile(lynx_path):
        print(f"Error: lynx.evt file not found at {lynx_path}")
        return teams

    import re

    with open(lynx_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split(',')]
            if not parts:
                continue

            # Athlete lines start with empty first column
            # Format: '', athleteId, lane, last, first, affiliation, ...
            if not parts[0] and len(parts) > 5:
                first_name = parts[4].strip() if len(parts) > 4 else ""
                affiliation = parts[5].strip()

                # Skip relay entries (no first name and affiliation matches pattern like 'ddcm  A')
                # Relay affiliations have 2-4 letters, spaces, then a single letter
                if not first_name and re.match(r'^\w{2,4}\s+\w$', affiliation):
                    continue

                if affiliation:
                    teams.add(affiliation)

    return teams


def load_existing_teams(colors_path):
    """Load existing team affiliations from colors.csv.

    Args:
        colors_path: Path to colors.csv file

    Returns:
        Set of existing team affiliation names
    """
    teams = set()

    if not os.path.isfile(colors_path):
        print(f"Warning: colors.csv file not found at {colors_path}")
        return teams

    with open(colors_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            affiliation = row.get('affiliation', '').strip()
            if affiliation:
                teams.add(affiliation)

    return teams


def add_missing_teams(colors_path, missing_teams):
    """Append missing teams to colors.csv with default values.

    Args:
        colors_path: Path to colors.csv file
        missing_teams: Set of team names to add
    """
    if not missing_teams:
        print("No missing teams to add.")
        return

    # Sort teams for consistent output
    sorted_teams = sorted(missing_teams)

    with open(colors_path, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for team in sorted_teams:
            # Format: affiliation, name, bgcolor, text
            # Default: black background (#000000), white text (#ffffff)
            writer.writerow([team, team, '#000000', '#ffffff'])
            print(f"Added: {team}")


def main():
    """Main script execution."""
    project_root = get_project_root()
    config_dir = project_root / 'config'

    lynx_path = config_dir / 'lynx.evt'
    colors_path = config_dir / 'colors.csv'

    print(f"Reading teams from: {lynx_path}")
    lynx_teams = parse_lynx_teams(lynx_path)
    print(f"Found {len(lynx_teams)} unique teams in lynx.evt")

    print(f"\nReading existing teams from: {colors_path}")
    existing_teams = load_existing_teams(colors_path)
    print(f"Found {len(existing_teams)} teams in colors.csv")

    # Find missing teams
    missing_teams = lynx_teams - existing_teams

    if missing_teams:
        print(f"\nFound {len(missing_teams)} missing teams:")
        for team in sorted(missing_teams):
            print(f"  - {team}")

        print(f"\nAdding missing teams to {colors_path}...")
        add_missing_teams(colors_path, missing_teams)
        print("\nDone!")
    else:
        print("\nAll teams from lynx.evt are already in colors.csv")


if __name__ == '__main__':
    main()
