"""
Acadience Learning Online progress monitoring extractor — authenticates with
the ALO API, requests the K-12 PM export, and returns a raw DataFrame.
No transformation happens here.
"""

import logging
from io import StringIO

import pandas as pd
import requests

from config.settings import ACADIENCE_LOGIN, acadience_pm_export_url


class AcadiencePMAuthError(Exception):
    pass


class AcadiencePMExportError(Exception):
    pass


def extract(year: str = "24") -> pd.DataFrame:
    """
    Authenticate with Acadience Learning Online and return the raw progress
    monitoring export as a DataFrame.

    Args:
        year: Acadience year code (e.g. "24" for the 2025-2026 school year).

    Raises:
        AcadiencePMAuthError: If login fails.
        AcadiencePMExportError: If the export request fails.
    """
    logger = logging.getLogger(__name__)
    session = requests.Session()

    logger.info("Authenticating with Acadience Learning Online...")
    login_response = session.post(
        ACADIENCE_LOGIN.url,
        json=ACADIENCE_LOGIN.payload,
        headers=ACADIENCE_LOGIN.headers,
    )

    if login_response.status_code != 200:
        raise AcadiencePMAuthError(
            f"Acadience login failed with status {login_response.status_code}"
        )

    if "acadience.authToken" not in session.cookies:
        raise AcadiencePMAuthError("Acadience login succeeded but no auth token was returned")

    url = acadience_pm_export_url(year)
    logger.info(f"Requesting Acadience PM export (year={year})...")

    response = session.get(url, headers=ACADIENCE_LOGIN.headers)

    if response.status_code != 200:
        raise AcadiencePMExportError(
            f"Acadience PM export failed with status {response.status_code}"
        )

    df = pd.read_csv(StringIO(response.content.decode("utf-8")), low_memory=False)
    logger.info(f"Fetched {len(df)} raw PM records (year={year})")
    return df
