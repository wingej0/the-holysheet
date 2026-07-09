"""
Aspire SIS extractor — authenticates with Aspire, requests the demographic
export, and returns a raw DataFrame. No transformation happens here.
"""

import logging
from io import StringIO

import pandas as pd
import requests

from config.settings import ASPIRE_EXPORT, ASPIRE_LOGIN


class AspireAuthError(Exception):
    pass


class AspireExportError(Exception):
    pass


def extract() -> pd.DataFrame:
    """
    Authenticate with Aspire and return the raw demographic export as a
    DataFrame. Raises AspireAuthError or AspireExportError on failure.
    """
    logger = logging.getLogger(__name__)
    session = requests.Session()

    try:
        # -------------------------------------------------------------------
        # Step 1: POST to login page to obtain the ASP.NET session cookie
        # -------------------------------------------------------------------
        init_response = session.post(ASPIRE_LOGIN.url, headers=ASPIRE_LOGIN.headers)
        cookie = init_response.cookies.get("ASP.NET_SessionId")

        if not cookie:
            raise AspireAuthError("Failed to obtain ASP.NET_SessionId from Aspire login page")

        cookie_header = f"ASP.NET_SessionId={cookie};"

        # -------------------------------------------------------------------
        # Step 2: POST credentials to authenticate
        # -------------------------------------------------------------------
        login_headers = {**ASPIRE_LOGIN.headers, "Cookie": cookie_header}

        logger.info("Authenticating with Aspire...")
        login_response = session.post(
            ASPIRE_LOGIN.url,
            data=ASPIRE_LOGIN.payload,
            headers=login_headers,
        )

        if login_response.status_code != 200:
            raise AspireAuthError(
                f"Aspire login failed with status {login_response.status_code}"
            )
    except AspireAuthError:
        raise
    except Exception as exc:
        raise AspireAuthError(f"Aspire authentication failed: {exc}") from exc

    try:
        # -------------------------------------------------------------------
        # Step 3: POST to export endpoint — bare request (not session) to avoid
        # redirect loops; cookie is passed manually as in the original scraper
        # -------------------------------------------------------------------
        export_headers = {**ASPIRE_EXPORT.headers, "Cookie": cookie_header}

        logger.info("Requesting demographic data export from Aspire...")
        export_response = requests.request(
            "POST",
            ASPIRE_EXPORT.url,
            data=ASPIRE_EXPORT.payload,
            headers=export_headers,
        )

        if export_response.status_code != 200:
            raise AspireExportError(
                f"Aspire export failed with status {export_response.status_code}"
            )

        # -------------------------------------------------------------------
        # Step 4: Parse CSV response into a DataFrame
        # -------------------------------------------------------------------
        csv_text = export_response.content.decode("utf-8")
        df = pd.read_csv(StringIO(csv_text))
    except AspireExportError:
        raise
    except Exception as exc:
        raise AspireExportError(f"Aspire export failed: {exc}") from exc

    logger.info(f"Fetched {len(df)} raw student records from Aspire")
    return df
