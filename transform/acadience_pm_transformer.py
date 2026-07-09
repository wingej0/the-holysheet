"""
Acadience PM transformer — selects, renames, deduplicates, and cleans the raw
progress monitoring export into a warehouse-ready DataFrame.

Returns a dict with:
    'pm'  → DataFrame for warehouse.fact_acadience_pm
"""

import logging

import pandas as pd

from transform.acadience_transformer import SCHOOL_NAME_MAP


RAW_COLS = [
    "Student State ID",
    "School Year",
    "Date",
    "School Name",
    "Student Grade Level",
    "Subject",
    "Score Type",
    "Monitor Level",
    "Score",
]

RENAME_MAP = {
    "Student State ID": "ssid",
    "School Year": "school_year",
    "Date": "assessment_date",
    "School Name": "school_name",
    "Student Grade Level": "grade",
    "Subject": "subject",
    "Score Type": "measure",
    "Monitor Level": "monitor_level",
    "Score": "score",
}

_PK = ["ssid", "school_year", "assessment_date", "measure"]


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform the raw Acadience PM export into a warehouse-ready DataFrame.

    Args:
        raw: DataFrame returned by extract.acadience_pm_extractor.extract()

    Returns:
        dict with key 'pm'
    """
    logger = logging.getLogger(__name__)

    # -----------------------------------------------------------------------
    # 1. Drop rows with no SSID
    # -----------------------------------------------------------------------
    no_ssid = raw["Student State ID"].isna().sum()
    df = raw.dropna(subset=["Student State ID"]).copy()
    if no_ssid:
        logger.warning(f"Dropped {no_ssid} rows with no Student State ID")

    # -----------------------------------------------------------------------
    # 2. Drop rows with no Score Type (measure) — can't link to a measure
    # -----------------------------------------------------------------------
    no_measure = df["Score Type"].isna().sum()
    df = df.dropna(subset=["Score Type"])
    if no_measure:
        logger.warning(f"Dropped {no_measure} rows with no Score Type (measure)")

    # -----------------------------------------------------------------------
    # 2b. Drop rows with no school name — can't link to a school
    # -----------------------------------------------------------------------
    no_school = (df["School Name"].isna() | (df["School Name"].str.strip() == "")).sum()
    df = df[df["School Name"].notna() & (df["School Name"].str.strip() != "")]
    if no_school:
        logger.warning(f"Dropped {no_school} rows with blank school name")

    # -----------------------------------------------------------------------
    # 3. Select and rename columns
    # -----------------------------------------------------------------------
    df = df[RAW_COLS].rename(columns=RENAME_MAP)

    # -----------------------------------------------------------------------
    # 4. Normalize school names
    # -----------------------------------------------------------------------
    df["school_name"] = df["school_name"].replace(SCHOOL_NAME_MAP)

    # -----------------------------------------------------------------------
    # 5. Parse types
    # -----------------------------------------------------------------------
    df["ssid"] = pd.to_numeric(df["ssid"], errors="coerce").astype("Int64")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df["monitor_level"] = pd.to_numeric(df["monitor_level"], errors="coerce")
    df["assessment_date"] = pd.to_datetime(df["assessment_date"], errors="coerce").dt.date

    unparseable_ssid = df["ssid"].isna().sum()
    df = df.dropna(subset=["ssid"])
    if unparseable_ssid:
        logger.warning(f"Dropped {unparseable_ssid} rows with unparseable SSID")

    # -----------------------------------------------------------------------
    # 6. Deduplicate — take median score when a measure is given multiple
    #    times on the same day (e.g. multiple ORF passages)
    # -----------------------------------------------------------------------
    pre_dedup = len(df)
    df = (
        df.groupby(_PK + ["school_name", "grade", "subject"], dropna=False)
        .agg(
            score=("score", "median"),
            monitor_level=("monitor_level", "first"),
        )
        .reset_index()
    )
    deduped = pre_dedup - len(df)
    if deduped:
        logger.info(f"Collapsed {deduped} duplicate rows via median score")

    # -----------------------------------------------------------------------
    # 7. Round median scores to integers (scores are always whole numbers)
    # -----------------------------------------------------------------------
    df["score"] = df["score"].round().astype("Int64")

    logger.info(
        f"Transformed {len(df)} PM records for {df['ssid'].nunique()} students "
        f"across {df['measure'].nunique()} measures"
    )

    return {"pm": df}
