"""
ACT extractor — reads the latest ACT roster CSV and all crosswalk files
from data/act/. Returns raw DataFrames for both.

Expected layout:
    data/act/act_{date}.csv          — roster export (one row per student per sitting)
    data/act/crosswalk_{year}.csv    — ACT ID → SSID crosswalk per year
"""

import logging
from pathlib import Path

import pandas as pd

ACT_DATA_DIR = Path("data/act")


class ActExtractError(Exception):
    pass


def extract() -> dict[str, pd.DataFrame]:
    """
    Read the latest ACT roster and all crosswalk files.

    Returns:
        Dict with keys:
            'roster'    — all test sittings from the most recent roster export
            'crosswalk' — combined ACT ID → SSID mapping from all crosswalk files

    Raises:
        ActExtractError: If the data directory is missing or required files not found.
    """
    logger = logging.getLogger(__name__)

    if not ACT_DATA_DIR.exists():
        raise ActExtractError(f"ACT data directory not found: {ACT_DATA_DIR}")

    # --- Roster: pick the latest act_*.csv ---
    roster_files = sorted(ACT_DATA_DIR.glob("act_*.csv"))
    if not roster_files:
        raise ActExtractError(f"No ACT roster files found in {ACT_DATA_DIR}")

    roster_file = roster_files[-1]
    # Skip 2 metadata rows + 1 blank line before the header
    roster = pd.read_csv(roster_file, skiprows=3)
    logger.info(f"Loaded roster {roster_file.name}: {len(roster)} rows")

    # --- Crosswalk: combine all crosswalk_*.csv files ---
    crosswalk_files = sorted(ACT_DATA_DIR.glob("crosswalk_*.csv"))
    if not crosswalk_files:
        raise ActExtractError(f"No crosswalk files found in {ACT_DATA_DIR}")

    frames = []
    for f in crosswalk_files:
        df = pd.read_csv(f, usecols=["ID_ACT", "ID_StateAssign"])
        frames.append(df)
        logger.info(f"Loaded crosswalk {f.name}: {len(df)} rows")

    crosswalk = pd.concat(frames, ignore_index=True)
    logger.info(f"Combined crosswalk: {len(crosswalk)} rows from {len(frames)} file(s)")

    return {"roster": roster, "crosswalk": crosswalk}
