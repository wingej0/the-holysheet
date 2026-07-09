"""
Aspire Plus transformer — renames camelCase columns to snake_case, selects
relevant scores, computes class rank and quartile within school/grade groups,
and returns a warehouse-ready DataFrame.

Note: ELAScaleScore and EnglishScaleScore exist in older years (≤22-23) but
were dropped by ACT in later releases. Optional columns are handled gracefully.

Input:  raw DataFrame from aspire_plus_extractor.extract()
Output: dict with key 'aspire_plus'
"""

import logging

import pandas as pd

from transform._ranking import add_rank_and_quartile

# Direct camelCase → snake_case rename map.
# Only columns in this map are selected; missing columns are silently skipped.
RENAME = {
    "school_year":                          "school_year",
    "LocalStudentID":                       "local_id",
    "StatewideStudentID":                   "ssid",
    "ActualGradeOfStudent":                 "grade",
    "ReportingSchoolNumber":                "school_number",
    # Composite
    "CompositeScaleScore":                  "composite_scale_score",
    "CompositePredictedACTScore":           "composite_predicted_act",
    "CompositePredictedACTScoreRangeLow":   "composite_predicted_act_low",
    "CompositePredictedACTScoreRangeHigh":  "composite_predicted_act_high",
    # ELA (older years only)
    "ELAScaleScore":                        "ela_scale_score",
    "ELAProficiencyLevel":                  "ela_proficiency",
    # STEM
    "STEMScaleScore":                       "stem_scale_score",
    "STEMProficiencyLevel":                 "stem_proficiency",
    # English (older years only)
    "EnglishScaleScore":                    "english_scale_score",
    "EnglishProficiencyLevel":              "english_proficiency",
    "EnglishPredictedACTScore":             "english_predicted_act",
    "EnglishPredictedACTScoreRangeLow":     "english_predicted_act_low",
    "EnglishPredictedACTScoreRangeHigh":    "english_predicted_act_high",
    # Reading
    "ReadingScaleScore":                    "reading_scale_score",
    "ReadingProficiencyLevel":              "reading_proficiency",
    "ReadingPredictedACTScore":             "reading_predicted_act",
    "ReadingPredictedACTScoreRangeLow":     "reading_predicted_act_low",
    "ReadingPredictedACTScoreRangeHigh":    "reading_predicted_act_high",
    # Math
    "MathScaleScore":                       "math_scale_score",
    "MathProficiencyLevel":                 "math_proficiency",
    "MathPredictedACTScore":                "math_predicted_act",
    "MathPredictedACTScoreRangeLow":        "math_predicted_act_low",
    "MathPredictedACTScoreRangeHigh":       "math_predicted_act_high",
    # Science
    "ScienceScaleScore":                    "science_scale_score",
    "ScienceProficiencyLevel":              "science_proficiency",
    "SciencePredictedACTScore":             "science_predicted_act",
    "SciencePredictedACTScoreRangeLow":     "science_predicted_act_low",
    "SciencePredictedACTScoreRangeHigh":    "science_predicted_act_high",
}

# Scale score columns to compute rank/quartile for
_SCORE_COLS = [
    ("composite_scale_score", "composite"),
    ("ela_scale_score",       "ela"),
    ("stem_scale_score",      "stem"),
    ("english_scale_score",   "english"),
    ("reading_scale_score",   "reading"),
    ("math_scale_score",      "math"),
    ("science_scale_score",   "science"),
]

_RANK_GROUP_COLS = ["school_year", "school_number", "grade"]


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform the raw Aspire Plus DataFrame into a warehouse-ready form.

    Args:
        raw: DataFrame from aspire_plus_extractor.extract().

    Returns:
        Dict with key 'aspire_plus'.
    """
    logger = logging.getLogger(__name__)

    # Select only columns present in this data (handles year-to-year schema changes)
    cols_to_keep = [c for c in RENAME if c in raw.columns]
    df = raw[cols_to_keep].rename(columns=RENAME).copy()

    # Drop rows with no local_id — can't link to a student
    before = len(df)
    df = df.dropna(subset=["local_id"]).reset_index(drop=True)
    if (dropped := before - len(df)):
        logger.warning(f"Dropped {dropped} rows with null local_id")

    # One row per student per year
    pk = ["local_id", "school_year"]
    dupes = df.duplicated(subset=pk, keep=False).sum()
    if dupes:
        logger.warning(f"{dupes} duplicate rows — keeping first per student/year")
    df = df.drop_duplicates(subset=pk, keep="first").reset_index(drop=True)

    # Coerce identifiers
    df["local_id"] = pd.to_numeric(df["local_id"], errors="coerce").astype("Int64")
    df["ssid"] = pd.to_numeric(df["ssid"], errors="coerce").astype("Int64")
    df["grade"] = pd.to_numeric(df["grade"], errors="coerce").astype("Int64")
    df["school_number"] = pd.to_numeric(df["school_number"], errors="coerce").astype("Int64")

    # Coerce all remaining columns to numeric
    non_numeric = {"local_id", "ssid", "grade", "school_number", "school_year"}
    for col in df.columns:
        if col not in non_numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute rank and quartile for each scale score present
    for score_col, prefix in _SCORE_COLS:
        if score_col in df.columns:
            df = add_rank_and_quartile(df, score_col, prefix, _RANK_GROUP_COLS)

    logger.info(
        f"Transformed {len(df)} Aspire Plus rows "
        f"({df['school_year'].nunique()} year(s), grades {sorted(df['grade'].dropna().unique().tolist())})"
    )
    return {"aspire_plus": df}
