"""
TOSCRF transformer — renames columns to snake_case, coerces types, and
computes rank/quartile on index_score within school/grade/year/window groups.

Quartile 4 = top 25% (highest index scores).

Input:  raw DataFrame from toscrf_extractor.extract()
Output: dict with key 'toscrf'
"""

import logging

import pandas as pd

from transform._ranking import add_rank_and_quartile

RENAME = {
    "ID":               "local_id",
    "School Name":      "school_name",
    "Grade":            "grade",
    "Form":             "form",
    "Test Date":        "test_date",
    "Raw Score":        "raw_score",
    "Age":              "age",
    "Age Equivalent":   "age_equivalent",
    "Grade Equivalent": "grade_equivalent",
    "Percentile Rank":  "percentile_rank",
    "Index Score":      "index_score",
    "Descriptive Term": "descriptive_term",
    "school_year":      "school_year",
    "assessment_window":           "assessment_window",
}

_RANK_GROUP_COLS = ["school_year", "assessment_window", "school_name", "grade"]


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform raw TOSCRF data into a warehouse-ready DataFrame.

    Args:
        raw: Combined DataFrame from toscrf_extractor.extract().

    Returns:
        Dict with key 'toscrf'.
    """
    logger = logging.getLogger(__name__)

    # Select and rename columns (drop Last Name, First Name, Birthday — in dim_students)
    cols_to_keep = [c for c in RENAME if c in raw.columns]
    df = raw[cols_to_keep].rename(columns=RENAME).copy()

    # Remove rows with no descriptive term (no valid score)
    before = len(df)
    df = df[df["descriptive_term"].notna() & (df["descriptive_term"] != "")]
    if (dropped := before - len(df)):
        logger.warning(f"Dropped {dropped} rows with no descriptive term")

    # Coerce types
    df["local_id"] = pd.to_numeric(df["local_id"], errors="coerce").astype("Int64")
    df["raw_score"] = pd.to_numeric(df["raw_score"], errors="coerce")
    df["index_score"] = pd.to_numeric(df["index_score"], errors="coerce")
    df["percentile_rank"] = pd.to_numeric(df["percentile_rank"], errors="coerce")

    # Drop rows with no local_id
    before = len(df)
    df = df.dropna(subset=["local_id"]).reset_index(drop=True)
    if (dropped := before - len(df)):
        logger.warning(f"Dropped {dropped} rows with null local_id")

    # Deduplicate on PK
    pk = ["local_id", "school_year", "assessment_window"]
    dupes = df.duplicated(subset=pk, keep=False).sum()
    if dupes:
        logger.warning(f"{dupes} duplicate rows on PK — keeping first")
    df = df.drop_duplicates(subset=pk, keep="first").reset_index(drop=True)

    # Rank and quartile on index_score — Quartile 4 = top 25%
    # TOSCRF has a single score column, so the warehouse schema uses bare
    # class_rank/quartile names rather than the helper's {name}_ prefix.
    df = add_rank_and_quartile(df, "index_score", "index", _RANK_GROUP_COLS)
    df = df.rename(columns={"index_class_rank": "class_rank", "index_quartile": "quartile"})

    # Final column order
    df = df[[
        "local_id", "school_year", "assessment_window", "school_name", "grade",
        "form", "test_date", "raw_score", "age", "age_equivalent",
        "grade_equivalent", "percentile_rank", "index_score",
        "descriptive_term", "class_rank", "quartile",
    ]]

    logger.info(
        f"Transformed {len(df)} TOSCRF rows "
        f"({df['school_year'].nunique()} year(s), "
        f"{df['assessment_window'].nunique()} window(s), "
        f"{df['local_id'].nunique()} unique students)"
    )
    return {"toscrf": df}
