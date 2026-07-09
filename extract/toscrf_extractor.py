"""
TOSCRF extractor — reads TOSCRF assessment data from Google Sheets.

Spreadsheets are named "{year} TOSCRF" (e.g. "24-25 TOSCRF").
Each spreadsheet has three worksheets: BOY, MOY, EOY.

Returns a flat list of DataFrames with school_year and window columns added.
"""

import logging

import gspread
import pandas as pd

from config.settings import GOOGLE_SERVICE_ACCOUNT_PATH

YEARS = ["24-25", "25-26"]
WINDOWS = ["BOY", "MOY", "EOY"]


class ToscrfExtractError(Exception):
    pass


def extract(years: list[str] | None = None) -> pd.DataFrame:
    """
    Read TOSCRF data from Google Sheets for all years and windows.

    Args:
        years: Year strings to load (e.g. ['24-25']). Defaults to all years.

    Returns:
        Combined DataFrame with school_year and window columns added.

    Raises:
        ToscrfExtractError: If authentication fails, a spreadsheet/worksheet
            can't be read for an unexpected reason, or no data is found.
    """
    logger = logging.getLogger(__name__)

    try:
        gc = gspread.service_account(GOOGLE_SERVICE_ACCOUNT_PATH)
    except Exception as exc:
        raise ToscrfExtractError(f"Google Sheets authentication failed: {exc}") from exc

    target_years = years or YEARS
    frames = []

    for year in target_years:
        try:
            spreadsheet = gc.open(f"{year} TOSCRF")
            logger.info(f"Opened spreadsheet: {year} TOSCRF")
        except gspread.exceptions.SpreadsheetNotFound:
            logger.warning(f"Spreadsheet not found: {year} TOSCRF — skipping")
            continue
        except Exception as exc:
            raise ToscrfExtractError(
                f"Failed to open spreadsheet {year} TOSCRF: {exc}"
            ) from exc

        for window in WINDOWS:
            try:
                ws = spreadsheet.worksheet(window)
                df = pd.DataFrame(ws.get_all_records())
                df["school_year"] = year
                df["assessment_window"] = window
                frames.append(df)
                logger.info(f"Fetched {year} TOSCRF {window}: {len(df)} rows")
            except gspread.exceptions.WorksheetNotFound:
                logger.warning(f"Worksheet not found: {year} TOSCRF → {window} — skipping")
            except Exception as exc:
                raise ToscrfExtractError(
                    f"Failed to read {year} TOSCRF {window}: {exc}"
                ) from exc

    if not frames:
        raise ToscrfExtractError("No TOSCRF data found across any year/window")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(
        f"Combined {len(frames)} sheet(s): {len(combined)} total rows"
    )
    return combined
