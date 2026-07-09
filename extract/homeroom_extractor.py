"""
Homeroom extractor — pulls current homeroom teacher assignments from the
Aspire SQL Server view LEA.GetHomeRoom_View. Returns one row per student.
"""

import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import SQL_SERVER


class HomeroomExtractError(Exception):
    pass


_SQL = text("""
    SELECT
        StudentID,
        SSID,
        schoolc         AS school_id,
        Abbrev          AS school_abbrev,
        Course          AS homeroom_course,
        TeacherLastName,
        TeacherFirstName
    FROM LEA.GetHomeRoom_View
""")


def _engine() -> Engine:
    return create_engine(SQL_SERVER.url, connect_args={"timeout": 30})


def extract() -> pd.DataFrame:
    """
    Return a DataFrame of current homeroom assignments, one row per student.

    Returns:
        DataFrame with columns: StudentID, SSID, school_id, school_abbrev,
                                homeroom_course, TeacherLastName, TeacherFirstName

    Raises:
        HomeroomExtractError: If the SQL query fails.
    """
    logger = logging.getLogger(__name__)
    logger.info("Querying homeroom assignments from SQL Server...")

    engine = _engine()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(_SQL, conn)
    except Exception as exc:
        raise HomeroomExtractError(f"Failed to extract homeroom data: {exc}") from exc
    finally:
        engine.dispose()

    logger.info(f"Fetched {len(df):,} homeroom assignments")
    return df
