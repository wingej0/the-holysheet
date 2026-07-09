"""
Acadience transformer — selects, renames, and cleans the raw benchmark export
into two warehouse-ready DataFrames: reading and math.

Returns a dict with:
    'reading'  → DataFrame for warehouse.fact_acadience_reading
    'math'     → DataFrame for warehouse.fact_acadience_math
"""

import logging

import pandas as pd

from transform._ranking import add_rank_and_quartile


# ---------------------------------------------------------------------------
# Column selection
# ---------------------------------------------------------------------------

# Shared context columns present in both reading and math tables
_CONTEXT_COLS = [
    "Student State ID",
    "School Year",
    "Benchmark Period",
    "School Name",
    "Student Grade Level",
]

READING_RAW_COLS = _CONTEXT_COLS + [
    "FSF Score", "FSF Status", "FSF National Percentile", "FSF Date",
    "LNF Score", "LNF National Percentile", "LNF Date",
    "PSF Score", "PSF Status", "PSF National Percentile", "PSF Date",
    "NWF CLS Score", "NWF CLS Status", "NWF CLS National Percentile",
    "NWF WWR Score", "NWF WWR Status", "NWF WWR National Percentile", "NWF Date",
    "ORF WC Score", "ORF WC Status", "ORF WC National Percentile",
    "ORF Accuracy Score", "ORF Accuracy Status", "ORF Accuracy National Percentile", "ORF Date",
    "Retell Score", "Retell Status", "Retell National Percentile",
    "Retell Quality Score", "Retell Quality Status",
    "Maze Adjusted Score", "Maze Status", "Maze National Percentile", "Maze Date",
    "Reading Composite Score", "Reading Composite Status",
    "Reading Composite Pathway", "Reading Composite National Percentile",
    "Reading Composite Date",
    "Lexile Reading",
]

MATH_RAW_COLS = _CONTEXT_COLS + [
    "BQD Score", "BQD Status", "BQD National Percentile", "BQD Date",
    "NIF Score", "NIF Status", "NIF National Percentile", "NIF Date",
    "NNF Score", "NNF Status", "NNF National Percentile", "NNF Date",
    "AQD Score", "AQD Status", "AQD National Percentile", "AQD Date",
    "MNF Score", "MNF Status", "MNF National Percentile", "MNF Date",
    "Comp Score", "Comp Status", "Comp National Percentile", "Comp Date",
    "C&A Score", "C&A Status", "C&A National Percentile", "C&A Date",
    "Math Composite Score", "Math Composite Status",
    "Math Composite Pathway", "Math Composite National Percentile",
    "Math Composite Date",
]

# ---------------------------------------------------------------------------
# Column rename maps
# ---------------------------------------------------------------------------

_CONTEXT_RENAME = {
    "Student State ID": "ssid",
    "School Year": "school_year",
    "Benchmark Period": "benchmark_period",
    "School Name": "school_name",
    "Student Grade Level": "grade",
}

READING_RENAME = {
    **_CONTEXT_RENAME,
    "FSF Score": "fsf_score", "FSF Status": "fsf_status",
    "FSF National Percentile": "fsf_national_percentile", "FSF Date": "fsf_date",
    "LNF Score": "lnf_score",
    "LNF National Percentile": "lnf_national_percentile", "LNF Date": "lnf_date",
    "PSF Score": "psf_score", "PSF Status": "psf_status",
    "PSF National Percentile": "psf_national_percentile", "PSF Date": "psf_date",
    "NWF CLS Score": "nwf_cls_score", "NWF CLS Status": "nwf_cls_status",
    "NWF CLS National Percentile": "nwf_cls_national_percentile",
    "NWF WWR Score": "nwf_wwr_score", "NWF WWR Status": "nwf_wwr_status",
    "NWF WWR National Percentile": "nwf_wwr_national_percentile", "NWF Date": "nwf_date",
    "ORF WC Score": "orf_wc_score", "ORF WC Status": "orf_wc_status",
    "ORF WC National Percentile": "orf_wc_national_percentile",
    "ORF Accuracy Score": "orf_accuracy_score", "ORF Accuracy Status": "orf_accuracy_status",
    "ORF Accuracy National Percentile": "orf_accuracy_national_percentile", "ORF Date": "orf_date",
    "Retell Score": "retell_score", "Retell Status": "retell_status",
    "Retell National Percentile": "retell_national_percentile",
    "Retell Quality Score": "retell_quality_score",
    "Retell Quality Status": "retell_quality_status",
    "Maze Adjusted Score": "maze_adjusted_score", "Maze Status": "maze_status",
    "Maze National Percentile": "maze_national_percentile", "Maze Date": "maze_date",
    "Reading Composite Score": "reading_composite_score",
    "Reading Composite Status": "reading_composite_status",
    "Reading Composite Pathway": "reading_composite_pathway",
    "Reading Composite National Percentile": "reading_composite_national_percentile",
    "Reading Composite Date": "reading_composite_date",
    "Lexile Reading": "lexile_reading",
}

MATH_RENAME = {
    **_CONTEXT_RENAME,
    "BQD Score": "bqd_score", "BQD Status": "bqd_status",
    "BQD National Percentile": "bqd_national_percentile", "BQD Date": "bqd_date",
    "NIF Score": "nif_score", "NIF Status": "nif_status",
    "NIF National Percentile": "nif_national_percentile", "NIF Date": "nif_date",
    "NNF Score": "nnf_score", "NNF Status": "nnf_status",
    "NNF National Percentile": "nnf_national_percentile", "NNF Date": "nnf_date",
    "AQD Score": "aqd_score", "AQD Status": "aqd_status",
    "AQD National Percentile": "aqd_national_percentile", "AQD Date": "aqd_date",
    "MNF Score": "mnf_score", "MNF Status": "mnf_status",
    "MNF National Percentile": "mnf_national_percentile", "MNF Date": "mnf_date",
    "Comp Score": "comp_score", "Comp Status": "comp_status",
    "Comp National Percentile": "comp_national_percentile", "Comp Date": "comp_date",
    "C&A Score": "ca_score", "C&A Status": "ca_status",
    "C&A National Percentile": "ca_national_percentile", "C&A Date": "ca_date",
    "Math Composite Score": "math_composite_score",
    "Math Composite Status": "math_composite_status",
    "Math Composite Pathway": "math_composite_pathway",
    "Math Composite National Percentile": "math_composite_national_percentile",
    "Math Composite Date": "math_composite_date",
}


SCHOOL_NAME_MAP = {
    "Blanding School":                  "Blanding Elementary School",
    "Blanding School (25104)":          "Blanding Elementary School",
    "Blanding School,Bluff School":     "Blanding Elementary School",
    "Bluff School":                     "Bluff Elementary School",
    "Bluff School (25108)":             "Bluff Elementary School",
    "La Sal School":                    "La Sal Elementary School",
    "La Sal School (25124)":            "La Sal Elementary School",
    "Montezuma Creek School":           "Montezuma Creek Elementary",
    "Montezuma Creek School (25136)":   "Montezuma Creek Elementary",
    "Montezuma Creek Elementary School":"Montezuma Creek Elementary",
    "Monticello School":                "Monticello Elementary School",
    "Monticello School (25140)":        "Monticello Elementary School",
    "Tse'Bii'Nidzisgai School":         "Tse'bii'nidzisgai Elementary",
    "Tse'Bii'Nidzisgai School (25148)": "Tse'bii'nidzisgai Elementary",
    "Tse'bii'nidzisgai Elementary School": "Tse'bii'nidzisgai Elementary",
}

_RANK_GROUP_COLS = ["school_year", "benchmark_period", "school_name", "grade"]


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform the raw Acadience export into warehouse-ready DataFrames.

    Args:
        raw: DataFrame returned by extract.acadience_extractor.extract()

    Returns:
        dict with keys 'reading' and 'math'
    """
    logger = logging.getLogger(__name__)

    # -----------------------------------------------------------------------
    # 1. Drop rows with no benchmark period — students not yet assessed
    # -----------------------------------------------------------------------
    unassessed = raw["Benchmark Period"].isna().sum()
    df = raw.dropna(subset=["Benchmark Period"]).copy()
    logger.info(f"Dropped {unassessed} unassessed rows (no benchmark period)")

    # -----------------------------------------------------------------------
    # 2. Drop rows with no SSID — can't link to a student
    # -----------------------------------------------------------------------
    no_ssid = df["Student State ID"].isna().sum()
    df = df.dropna(subset=["Student State ID"]).copy()
    if no_ssid:
        logger.warning(f"Dropped {no_ssid} rows with no Student State ID")

    # -----------------------------------------------------------------------
    # 2b. Drop rows with no school name — can't link to a school
    # -----------------------------------------------------------------------
    no_school = (df["School Name"].isna() | (df["School Name"].str.strip() == "")).sum()
    df = df[df["School Name"].notna() & (df["School Name"].str.strip() != "")].copy()
    if no_school:
        logger.warning(f"Dropped {no_school} rows with blank school name")

    # -----------------------------------------------------------------------
    # 3. Deduplicate — keep one row per student/year/period
    #    (a student can appear multiple times if in multiple classes)
    # -----------------------------------------------------------------------
    pk = ["Student State ID", "School Year", "Benchmark Period"]
    dupes = df.duplicated(subset=pk, keep=False).sum()
    if dupes:
        logger.warning(f"{dupes} duplicate rows found — keeping first per student/year/period")
    df = df.drop_duplicates(subset=pk, keep="first")

    # -----------------------------------------------------------------------
    # 4. Build reading and math DataFrames
    # -----------------------------------------------------------------------
    reading = (
        df[READING_RAW_COLS]
        .rename(columns=READING_RENAME)
        .reset_index(drop=True)
    )

    math = (
        df[MATH_RAW_COLS]
        .rename(columns=MATH_RENAME)
        .reset_index(drop=True)
    )

    # -----------------------------------------------------------------------
    # 5. Normalize school names
    # -----------------------------------------------------------------------
    for df_ in (reading, math):
        df_["school_name"] = df_["school_name"].replace(SCHOOL_NAME_MAP)

    # -----------------------------------------------------------------------
    # 6. Coerce score and percentile columns to numeric — the CSV can return
    #    mixed types that pandas reads as object (text). Status, pathway, and
    #    context columns are left as-is.
    # -----------------------------------------------------------------------
    text_cols = {
        "ssid", "school_year", "benchmark_period", "school_name", "grade",
        "fsf_status", "psf_status", "nwf_cls_status", "nwf_wwr_status",
        "orf_wc_status", "orf_accuracy_status", "retell_status",
        "retell_quality_status", "maze_status", "reading_composite_status",
        "reading_composite_pathway", "lexile_reading",
        "bqd_status", "nif_status", "nnf_status", "aqd_status", "mnf_status",
        "comp_status", "ca_status", "math_composite_status",
        "math_composite_pathway",
    }
    date_cols = {
        "fsf_date", "lnf_date", "psf_date", "nwf_date", "orf_date",
        "maze_date", "reading_composite_date",
        "bqd_date", "nif_date", "nnf_date", "aqd_date", "mnf_date",
        "comp_date", "ca_date", "math_composite_date",
    }
    for df_ in (reading, math):
        for col in df_.columns:
            if col not in text_cols and col not in date_cols:
                df_[col] = pd.to_numeric(df_[col], errors="coerce")
        for col in date_cols:
            if col in df_.columns:
                df_[col] = pd.to_datetime(df_[col], errors="coerce").dt.date

    # -----------------------------------------------------------------------
    # 7. Add class rank and quartile for composite scores
    # -----------------------------------------------------------------------
    reading = add_rank_and_quartile(
        reading, "reading_composite_score", "reading_composite", _RANK_GROUP_COLS
    )
    math = add_rank_and_quartile(
        math, "math_composite_score", "math_composite", _RANK_GROUP_COLS
    )

    logger.info(
        f"Transformed {len(reading)} reading rows, {len(math)} math rows "
        f"({df['Benchmark Period'].nunique()} benchmark periods)"
    )

    return {"reading": reading, "math": math}
