"""
Acadience Learning Online extractor — authenticates with the ALO API,
requests the K-6 combined benchmark export, and returns a raw DataFrame.
Also supports loading historical data from local CSV files.
No transformation happens here.
"""

import logging
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from config.settings import ACADIENCE_LOGIN, acadience_export_url

LONGITUDINAL_DATA_DIR = Path("data/acadience/longitudinal_data")


class AcadienceAuthError(Exception):
    pass


class AcadienceExportError(Exception):
    pass


def extract(year: str = "24") -> pd.DataFrame:
    """
    Authenticate with Acadience Learning Online and return the raw benchmark
    export as a DataFrame.

    Args:
        year: Acadience year code (e.g. "24" for the 2025-2026 school year).

    Raises:
        AcadienceAuthError: If login fails.
        AcadienceExportError: If the export request fails.
    """
    logger = logging.getLogger(__name__)
    session = requests.Session()

    # -----------------------------------------------------------------------
    # Step 1: POST credentials — session captures the acadience.authToken cookie
    # -----------------------------------------------------------------------
    logger.info("Authenticating with Acadience Learning Online...")
    login_response = session.post(
        ACADIENCE_LOGIN.url,
        json=ACADIENCE_LOGIN.payload,
        headers=ACADIENCE_LOGIN.headers,
    )

    if login_response.status_code != 200:
        raise AcadienceAuthError(
            f"Acadience login failed with status {login_response.status_code}"
        )

    if "acadience.authToken" not in session.cookies:
        raise AcadienceAuthError("Acadience login succeeded but no auth token was returned")

    # -----------------------------------------------------------------------
    # Step 2: GET the benchmark export CSV
    # -----------------------------------------------------------------------
    url = acadience_export_url(year)
    logger.info(f"Requesting Acadience benchmark export (year={year})...")

    export_response = session.get(url, headers=ACADIENCE_LOGIN.headers)

    if export_response.status_code != 200:
        raise AcadienceExportError(
            f"Acadience export failed with status {export_response.status_code}"
        )

    # -----------------------------------------------------------------------
    # Step 3: Parse CSV response into a DataFrame
    # -----------------------------------------------------------------------
    df = pd.read_csv(StringIO(export_response.content.decode("utf-8")))
    logger.info(f"Fetched {len(df)} raw Acadience records (year={year})")
    return df


def extract_historical() -> pd.DataFrame:
    """
    Load all historical Acadience data from local CSV files in
    data/acadience/longitudinal_data/ and return as a single DataFrame.

    Returns:
        Combined DataFrame of all historical years, or empty DataFrame if
        no CSV files are found.
    """
    logger = logging.getLogger(__name__)
    frames = []

    csv_files = sorted(LONGITUDINAL_DATA_DIR.glob("*.csv"))
    if not csv_files:
        logger.warning(f"No CSV files found in {LONGITUDINAL_DATA_DIR}")
        return pd.DataFrame()

    for csv_file in csv_files:
        df = pd.read_csv(csv_file)
        frames.append(df)
        logger.info(f"Loaded {len(df)} rows from {csv_file.name}")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"Loaded {len(combined)} total historical Acadience rows from {len(frames)} files")
    return combined
