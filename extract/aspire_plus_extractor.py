"""
Aspire Plus extractor — reads local CSV files (one per year) and returns
a single concatenated DataFrame with a school_year column added.
No transformation here.

Expected layout:
    data/aspire_plus/{year}.csv
    e.g. data/aspire_plus/24-25.csv
"""

import logging
from pathlib import Path

import pandas as pd

ASPIRE_PLUS_DATA_DIR = Path("data/aspire_plus")


class AspirePlusExtractError(Exception):
    pass


def extract(years: list[str] | None = None) -> pd.DataFrame:
    """
    Read Aspire Plus CSV files and return a single concatenated DataFrame.

    Args:
        years: Year strings to load (e.g. ['23-24', '24-25']).
               If None, loads all CSVs found in ASPIRE_PLUS_DATA_DIR.

    Returns:
        DataFrame with all years concatenated and a 'school_year' column added.

    Raises:
        AspirePlusExtractError: If the data directory is missing, no files are
            found, or a found file can't be read/parsed.
    """
    logger = logging.getLogger(__name__)

    if not ASPIRE_PLUS_DATA_DIR.exists():
        raise AspirePlusExtractError(
            f"Aspire Plus data directory not found: {ASPIRE_PLUS_DATA_DIR}"
        )

    if years is None:
        csv_files = sorted(ASPIRE_PLUS_DATA_DIR.glob("*.csv"))
    else:
        csv_files = [ASPIRE_PLUS_DATA_DIR / f"{y}.csv" for y in years]

    if not csv_files:
        raise AspirePlusExtractError(
            f"No CSV files found in {ASPIRE_PLUS_DATA_DIR}"
        )

    frames = []
    for csv_file in csv_files:
        if not csv_file.exists():
            logger.warning(f"Not found (skipping): {csv_file}")
            continue
        try:
            df = pd.read_csv(csv_file)
        except (pd.errors.ParserError, UnicodeDecodeError, OSError) as exc:
            raise AspirePlusExtractError(f"Error reading {csv_file}: {exc}") from exc

        df["school_year"] = csv_file.stem
        frames.append(df)
        logger.info(f"Loaded {csv_file.name}: {len(df)} rows")

    if not frames:
        raise AspirePlusExtractError("No Aspire Plus data files could be read")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"Combined {len(frames)} file(s): {len(combined)} total rows")
    return combined
