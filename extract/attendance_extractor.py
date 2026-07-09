"""
Attendance extractor — pulls per-period attendance from the Aspire MSSQL
view SJSD_CSS.dbo.AttendanceArchive and aggregates to per-student-per-day
rows server-side (the raw view has ~1.4M rows per school year).
"""

import logging
from collections.abc import Sequence

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import SQL_SERVER


class AttendanceExtractError(Exception):
    pass


_AGG_SQL = text("""
    SELECT
        suniq                                         AS local_id,
        ddate                                         AS date,
        MAX(SchoolYear)                               AS school_year,
        MAX(termnum)                                  AS term,
        MAX(trkuniq)                                  AS school_id,
        COUNT(*)                                      AS periods,
        SUM(CASE WHEN inclass = 0 THEN 1 ELSE 0 END)  AS absences,
        SUM(CAST(ExcusedAbsenceFlag AS INT))          AS excused_absences,
        SUM(CAST(UnexcusedAbsenceFlag AS INT))        AS unexcused_absences,
        SUM(CAST(istardy AS INT))                     AS tardies
    FROM SJSD_CSS.dbo.AttendanceArchive
    WHERE SchoolYear = :school_year
    GROUP BY suniq, ddate
""")


def _engine() -> Engine:
    return create_engine(SQL_SERVER.url, connect_args={"timeout": 30})


def extract(school_year: int, engine: Engine | None = None) -> pd.DataFrame:
    """
    Return a DataFrame of per-student-per-day attendance for one school year.

    Args:
        school_year: Aspire's integer school year (e.g. 2026 for the 25-26 year).
        engine: Optional engine to reuse (e.g. from extract_all). A new one-off
            engine is created and disposed if not given.

    Raises:
        AttendanceExtractError: If the query fails.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Querying attendance for school_year={school_year}...")

    owns_engine = engine is None
    engine = engine or _engine()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(_AGG_SQL, conn, params={"school_year": school_year})
    except Exception as exc:
        raise AttendanceExtractError(
            f"Failed to extract attendance for {school_year}: {exc}"
        ) from exc
    finally:
        if owns_engine:
            engine.dispose()

    logger.info(f"Fetched {len(df):,} per-day rows for school_year={school_year}")
    return df


def extract_all(school_years: Sequence[int] = range(2021, 2027)) -> pd.DataFrame:
    """
    Return attendance rows for multiple school years concatenated into one DataFrame.

    Args:
        school_years: Years to pull (default 2021-2026).

    Raises:
        AttendanceExtractError: If any school year fails to extract, or if
            school_years is empty.
    """
    logger = logging.getLogger(__name__)
    engine = _engine()
    try:
        frames = [extract(year, engine=engine) for year in school_years]
    finally:
        engine.dispose()

    if not frames:
        raise AttendanceExtractError("No school years given to extract.")

    combined = pd.concat(frames, ignore_index=True)
    logger.info(f"Combined {len(combined):,} rows across {len(frames)} years")
    return combined
