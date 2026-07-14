"""
Attendance transformer — the extractor already aggregates per-student-per-day
server-side, so this module just normalizes types and drops rows with null
identifiers. Returns a single DataFrame under the 'attendance' key.
"""

import logging

import pandas as pd


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    logger = logging.getLogger(__name__)

    df = raw.copy()

    before = len(df)
    df = df.dropna(subset=["local_id", "date"]).reset_index(drop=True)
    dropped = before - len(df)
    if dropped:
        logger.warning(f"Dropped {dropped} rows with null local_id or date")

    df["local_id"] = df["local_id"].astype(int)
    df["school_year"] = df["school_year"].astype(int)
    df["term"] = df["term"].astype(int)
    df["school_id"] = df["school_id"].astype(int)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    for col in ("periods", "absences", "excused_absences", "unexcused_absences", "tardies"):
        df[col] = df[col].astype(int)

    logger.info(
        f"Transformed {len(df):,} attendance rows "
        f"({df['local_id'].nunique():,} students, {df['school_year'].nunique()} years)"
    )
    return {"attendance": df}
