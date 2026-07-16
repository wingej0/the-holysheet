"""
WIDA transformer — pivots long-format domain scores to wide format and
converts Year to school_year.

Input:  raw DataFrame from wida_extractor.extract()
Output: dict with key 'wida'
"""

import logging

import pandas as pd

# Maps "Proficiency Level - X" → snake_case column name
_DOMAIN_MAP = {
    "Proficiency Level - Overall":       "overall",
    "Proficiency Level - Listening":     "listening",
    "Proficiency Level - Speaking":      "speaking",
    "Proficiency Level - Reading":       "reading",
    "Proficiency Level - Writing":       "writing",
    "Proficiency Level - Comprehension": "comprehension",
    "Proficiency Level - Literacy":      "literacy",
    "Proficiency Level - Oral":          "oral",
}


def _year_to_school_year(year: int) -> str:
    """2024 → '23-24'  (WIDA reported after spring administration)"""
    return f"{str(year - 1)[2:]}-{str(year)[2:]}"


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform long-format WIDA data into one wide row per student per year.

    Args:
        raw: DataFrame from wida_extractor.extract().

    Returns:
        Dict with key 'wida'.
    """
    logger = logging.getLogger(__name__)

    df = raw.copy()

    # Keep only known domains
    before = len(df)
    df = df[df["Title"].isin(_DOMAIN_MAP)].copy()
    if (dropped := before - len(df)):
        logger.warning(f"Dropped {dropped} rows with unrecognized domain Title")

    # Remove blank/NA scores
    before = len(df)
    df = df[df["Score"].notna() & (df["Score"] != "") & (df["Score"] != "NA")]
    if (dropped := before - len(df)):
        logger.warning(f"Dropped {dropped} rows with blank/NA score")

    # Coerce Score to numeric
    df["Score"] = pd.to_numeric(df["Score"], errors="coerce")
    before = len(df)
    df = df.dropna(subset=["Score"])
    if (dropped := before - len(df)):
        logger.warning(f"Dropped {dropped} rows with non-numeric score")

    # Deduplicate on (StudentID, Year, Title) — one score per domain per student per year
    dupes = df.duplicated(subset=["StudentID", "Year", "Title"], keep=False).sum()
    if dupes:
        logger.warning(f"{dupes} duplicate rows on student/year/domain — keeping first")
    df = df.drop_duplicates(subset=["StudentID", "Year", "Title"], keep="first")

    # Pivot: one row per (StudentID, Year), domains as columns
    wide = df.pivot_table(
        index=["StudentID", "Year"],
        columns="Title",
        values="Score",
        aggfunc="first",
    ).reset_index()

    # Flatten column names and rename
    wide.columns.name = None
    wide = wide.rename(columns=_DOMAIN_MAP)
    wide = wide.rename(columns={"StudentID": "local_id"})

    # Convert Year → school_year string
    wide["school_year"] = wide["Year"].apply(_year_to_school_year)
    wide = wide.drop(columns=["Year"])

    # Coerce local_id
    wide["local_id"] = pd.to_numeric(wide["local_id"], errors="coerce").astype("Int64")

    # Final column order
    id_cols = ["local_id", "school_year"]
    score_cols = [c for c in _DOMAIN_MAP.values() if c in wide.columns]
    wide = wide[id_cols + score_cols]

    logger.info(
        f"Transformed {len(wide)} WIDA rows "
        f"({wide['school_year'].nunique()} year(s), "
        f"{wide['local_id'].nunique()} unique students)"
    )
    return {"wida": wide}
