"""
Enrollment extractor — pulls membership detail from the Aspire MSSQL
table-valued function LEA.Enrollment_Membership_Detail2_ITVF.

Each row represents one student enrollment track for the year. Students
who transferred schools mid-year will have multiple rows (one per school).
"""

import logging
from collections.abc import Sequence

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import SQL_SERVER


class EnrollmentExtractError(Exception):
    pass


def _engine() -> Engine:
    return create_engine(SQL_SERVER.url, connect_args={"timeout": 30})


def extract(school_year: int, engine: Engine | None = None) -> pd.DataFrame:
    """
    Return a DataFrame of enrollment membership rows for one school year.

    Args:
        school_year: Aspire's integer school year (e.g. 2025 for the 2024-25 year).
        engine: Optional engine to reuse (e.g. from extract_all). A new one-off
            engine is created and disposed if not given.

    Raises:
        EnrollmentExtractError: If the query fails.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Querying enrollment for school_year={school_year}...")

    sql = text("SELECT * FROM LEA.Enrollment_Membership_Detail2_ITVF(:school_year)")

    owns_engine = engine is None
    engine = engine or _engine()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params={"school_year": school_year})
    except Exception as exc:
        raise EnrollmentExtractError(
            f"Failed to extract enrollment for {school_year}: {exc}"
        ) from exc
    finally:
        if owns_engine:
            engine.dispose()

    logger.info(f"Fetched {len(df):,} enrollment rows for school_year={school_year}")
    return df


def extract_all(school_years: Sequence[int] = range(2021, 2027)) -> pd.DataFrame:
    """
    Return enrollment rows for multiple school years concatenated into one DataFrame.

    Args:
        school_years: Years to pull (default 2021-2026).

    Raises:
        EnrollmentExtractError: If any school year fails to extract, or if
            school_years is empty.
    """
    logger = logging.getLogger(__name__)
    engine = _engine()
    try:
        frames = [extract(year, engine=engine) for year in school_years]
    finally:
        engine.dispose()

    if not frames:
        raise EnrollmentExtractError("No enrollment data extracted for any year.")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"Combined {len(combined):,} rows across {len(frames)} years")
    return combined
