"""
WIDA extractor — pulls WIDA ACCESS proficiency scores from the Aspire SQL
Server view LEA.WingetAssessmentScores_View.

Data is in long format (one row per student per domain per year).
Transformation to wide format happens in the transformer.
"""

import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import SQL_SERVER


class WidaExtractError(Exception):
    pass


_SQL = text("""
    SELECT
        StudentID,
        Year,
        Title,
        Score
    FROM LEA.WingetAssessmentScores_View
    WHERE ShortTitle = 'WIDA ACCESS'
""")


def _engine() -> Engine:
    return create_engine(SQL_SERVER.url, connect_args={"timeout": 30})


def extract() -> pd.DataFrame:
    """
    Return a long-format DataFrame of all WIDA ACCESS scores.

    Returns:
        DataFrame with columns: StudentID, Year, Title, Score

    Raises:
        WidaExtractError: If the SQL query fails.
    """
    logger = logging.getLogger(__name__)
    logger.info("Querying WIDA ACCESS scores from SQL Server...")

    engine = _engine()
    try:
        with engine.connect() as conn:
            df = pd.read_sql(_SQL, conn)
    except Exception as exc:
        raise WidaExtractError(f"Failed to extract WIDA data: {exc}") from exc
    finally:
        engine.dispose()

    logger.info(
        f"Fetched {len(df):,} rows — "
        f"{df['StudentID'].nunique()} students, "
        f"years {sorted(df['Year'].unique())}"
    )
    return df
