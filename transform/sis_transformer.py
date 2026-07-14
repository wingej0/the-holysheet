"""
Aspire SIS transformer — selects, renames, cleans, and reshapes the raw
demographic export into warehouse-ready DataFrames.

Returns a dict with:
    'students'  → DataFrame for warehouse.dim_students
    'schools'   → DataFrame for warehouse.dim_schools
"""

import logging

import pandas as pd


# ---------------------------------------------------------------------------
# Column selection — subset of the 158-column raw export
# ---------------------------------------------------------------------------

RAW_COLS = [
    "FERPA Opt Out",
    "Student ID",
    "SSID",
    "Student Preferred Last Name",
    "Student Preferred First Name",
    "Student Legal Last Name",
    "Student Legal First Name",
    "Student Sex",
    "Student Birth Date",
    "Grade Level",
    "Student Ethnicity",
    "Student Race",
    "Student Home City",
    "School Code",
    "School Name",
    "Student Entry Date",
    "Student Exit Date",
    "Student Exit Code",
    "Economically Disadvantaged",
    "IEP Disability",
    "Tribal Affiliation",
    "YIC",
    "ELL",
    "Homeless",
    "Migrant",
    "Student Email Address",
    "Contact1 Last Name",
    "Contact1 First Name",
    "Contact1 Email Address",
]

RENAME_MAP = {
    "FERPA Opt Out": "ferpa_opt_out",
    "Student ID": "local_id",
    "SSID": "ssid",
    "Student Preferred Last Name": "preferred_last",
    "Student Preferred First Name": "preferred_first",
    "Student Legal Last Name": "legal_last",
    "Student Legal First Name": "legal_first",
    "Student Sex": "gender",
    "Student Birth Date": "date_of_birth",
    "Grade Level": "grade",
    "Student Ethnicity": "ethnicity",
    "Student Race": "race",
    "Student Home City": "home_city",
    "School Code": "school_id",
    "School Name": "school_name",
    "Student Entry Date": "entry_date",
    "Student Exit Date": "exit_date",
    "Student Exit Code": "exit_code",
    "Economically Disadvantaged": "economically_disadvantaged",
    "IEP Disability": "iep_disability",
    "Tribal Affiliation": "tribal_affiliation",
    "YIC": "yic",
    "ELL": "ell",
    "Homeless": "homeless",
    "Migrant": "migrant",
    "Student Email Address": "email",
    "Contact1 Last Name": "contact1_last",
    "Contact1 First Name": "contact1_first",
    "Contact1 Email Address": "contact1_email",
}


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform the raw Aspire export into warehouse-ready DataFrames.

    Args:
        raw: DataFrame returned by extract.sis_extractor.extract()

    Returns:
        dict with keys 'students' and 'schools'
    """
    logger = logging.getLogger(__name__)

    # -----------------------------------------------------------------------
    # 1. Select and rename columns
    # -----------------------------------------------------------------------
    df = raw[RAW_COLS].copy()
    df = df.rename(columns=RENAME_MAP)

    # -----------------------------------------------------------------------
    # 2. Drop preschool students (Grade Level -1 in Aspire)
    # -----------------------------------------------------------------------
    pre_k_count = (df["grade"] == -1).sum()
    df = df[df["grade"] != -1].copy()
    logger.info(f"Dropped {pre_k_count} preschool students (grade -1)")

    # -----------------------------------------------------------------------
    # 2. Parse dates
    # -----------------------------------------------------------------------
    for col in ["date_of_birth", "entry_date", "exit_date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # -----------------------------------------------------------------------
    # 3. Derive display name — preferred name, fallback to legal if blank
    # -----------------------------------------------------------------------
    df["display_first"] = df["preferred_first"].fillna("").str.strip()
    df.loc[df["display_first"] == "", "display_first"] = df["legal_first"].str.strip()

    df["display_last"] = df["preferred_last"].fillna("").str.strip()
    df.loc[df["display_last"] == "", "display_last"] = df["legal_last"].str.strip()

    # -----------------------------------------------------------------------
    # 4. Derive is_active — True if no exit code on record.
    # Aspire sets exit_date to end-of-year for all students; exit_code is
    # only populated when a student actually withdraws.
    # -----------------------------------------------------------------------
    df["is_active"] = df["exit_code"].isna()

    # -----------------------------------------------------------------------
    # 5. Build dim_schools from unique school_id + school_name pairs
    # -----------------------------------------------------------------------
    schools = (
        df[["school_id", "school_name"]]
        .drop_duplicates()
        .dropna(subset=["school_id"])
        .sort_values("school_id")
        .reset_index(drop=True)
    )

    # -----------------------------------------------------------------------
    # 6. Drop school_name from students — it lives in dim_schools
    # -----------------------------------------------------------------------
    students = df.drop(columns=["school_name"])

    # -----------------------------------------------------------------------
    # 7. Deduplicate dual-enrolled students — keep the record with the lowest
    # school_id (elementary schools have the lowest IDs in this district)
    # -----------------------------------------------------------------------
    dupes = students[students.duplicated("local_id", keep=False)]
    if not dupes.empty:
        dual_enrolled = dupes["local_id"].unique().tolist()
        logger.warning(
            f"Dual-enrolled students found ({len(dual_enrolled)}): {dual_enrolled} "
            f"— keeping record with lowest school_id for each"
        )
    students = (
        students.sort_values("school_id")
        .drop_duplicates(subset="local_id", keep="first")
        .reset_index(drop=True)
    )

    logger.info(
        f"Transformed {len(students)} students across {len(schools)} schools"
    )

    return {"students": students, "schools": schools}
