"""
ACT transformer — renames columns to snake_case, joins crosswalk for SSIDs,
derives school_year from test_date, and computes rank/quartile per school/year.

Input:  dict with 'roster' and 'crosswalk' from act_extractor.extract()
Output: dict with key 'act'
"""

import logging
from datetime import datetime

import pandas as pd

from transform._ranking import add_rank_and_quartile

RENAME = {
    "ACT ID":               "act_id",
    "Test Date":            "test_date",
    "ACT composite score":  "composite_score",
    "ACT English score":    "english_score",
    "ACT math score":       "math_score",
    "ACT reading score":    "reading_score",
    "ACT science score":    "science_score",
    "ACT STEM score":       "stem_score",
    "School Org Number":    "school_org_number",
}

_SCORE_COLS = [
    ("composite_score", "composite"),
    ("english_score",   "english"),
    ("math_score",      "math"),
    ("reading_score",   "reading"),
    ("science_score",   "science"),
    ("stem_score",      "stem"),
]

_RANK_GROUP_COLS = ["school_year", "school_org_number"]


def _test_date_to_school_year(test_date: str) -> str:
    """'March 2025' → '24-25',  'October 2024' → '24-25'"""
    dt = datetime.strptime(test_date, "%B %Y")
    if dt.month >= 7:
        return f"{str(dt.year)[2:]}-{str(dt.year + 1)[2:]}"
    return f"{str(dt.year - 1)[2:]}-{str(dt.year)[2:]}"


def transform(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Transform raw ACT roster and crosswalk into a warehouse-ready DataFrame.

    Args:
        raw: Dict with 'roster' and 'crosswalk' from act_extractor.extract().

    Returns:
        Dict with key 'act'.
    """
    logger = logging.getLogger(__name__)

    roster = raw["roster"]
    crosswalk = raw["crosswalk"]

    # Select and rename columns
    cols_to_keep = [c for c in RENAME if c in roster.columns]
    df = roster[cols_to_keep].rename(columns=RENAME).copy()

    # Build crosswalk lookup: deduplicate on act_id, prefer entries with an SSID
    cw = (
        crosswalk
        .rename(columns={"ID_ACT": "act_id", "ID_StateAssign": "ssid"})
        .dropna(subset=["ssid"])
        .drop_duplicates(subset=["act_id"], keep="first")
    )
    cw["act_id"] = cw["act_id"].astype(str)
    df["act_id"] = df["act_id"].astype(str)

    df = df.merge(cw[["act_id", "ssid"]], on="act_id", how="left")

    # Derive school year from test date text
    df["school_year"] = df["test_date"].map(_test_date_to_school_year)

    # Coerce types
    df["ssid"] = pd.to_numeric(df["ssid"], errors="coerce").astype("Int64")
    df["school_org_number"] = pd.to_numeric(df["school_org_number"], errors="coerce").astype("Int64")
    for score_col, _ in _SCORE_COLS:
        df[score_col] = pd.to_numeric(df[score_col], errors="coerce").astype("Int64")

    # Rank and quartile per school/year
    for score_col, prefix in _SCORE_COLS:
        df = add_rank_and_quartile(df, score_col, prefix, _RANK_GROUP_COLS)

    # Final column order
    id_cols = ["act_id", "ssid", "test_date", "school_year", "school_org_number"]
    score_cols = [
        col
        for pair in _SCORE_COLS
        for col in [pair[0], f"{pair[1]}_class_rank", f"{pair[1]}_quartile"]
    ]
    df = df[id_cols + score_cols]

    # Drop exact duplicates on PK — roster can contain duplicate rows
    before = len(df)
    df = df.drop_duplicates(subset=["act_id", "test_date"], keep="first").reset_index(drop=True)
    if (dropped := before - len(df)):
        logger.warning(f"Dropped {dropped} duplicate (act_id, test_date) rows from roster")

    missing_ssid = df["ssid"].isna().sum()
    if missing_ssid:
        logger.warning(f"{missing_ssid} rows have no SSID match in crosswalk")

    logger.info(
        f"Transformed {len(df)} ACT rows "
        f"({df['school_year'].nunique()} year(s), "
        f"{df['act_id'].nunique()} unique students)"
    )
    return {"act": df}
