"""
Enrollment transformer — renames and cleans the raw membership detail into
a warehouse-ready DataFrame for fact_enrollment.

Key derived column:
    enrolled_160_days — True if Membership >= 160 (used to filter students
                        who were meaningfully present for the full year).
"""

import logging

import pandas as pd


_RENAME = {
    "trkuniq":              "track_id",
    "schoolc":              "school_code",
    "SchoolAbbrev":         "school_abbrev",
    "schyear":              "school_year",
    "stuuniq":              "aspire_student_id",
    "StudentID":            "local_id",
    "SSID":                 "ssid",
    "RowStudentYear":       "row_student_year",
    "RowStudentTrack":      "row_student_track",
    "edate":                "entry_date",
    "xdate":                "exit_date",
    "entryc":               "entry_code",
    "exitc":                "exit_code",
    "stustatc":             "student_status",
    "graden":               "grade",
    "IsPartTime":           "is_part_time",
    "ResidencyCode":        "residency_code",
    "MembershipMultiplier": "membership_multiplier",
    "IsProjected":          "is_projected",
    "DayCount":             "day_count",
    "Membership":           "membership",
}

# Columns from the raw export to drop (human-readable labels already
# captured by the code columns above)
_DROP = ["SchoolYear", "EntryCode", "ExitCode", "Residency"]


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform the raw enrollment extract into a warehouse-ready DataFrame.

    Returns:
        dict with key 'enrollment'
    """
    logger = logging.getLogger(__name__)

    df = raw.drop(columns=_DROP, errors="ignore").rename(columns=_RENAME)

    # Coerce types — use float then nullable int to avoid psycopg2 issues
    df["school_year"]         = pd.to_numeric(df["school_year"], errors="coerce").astype(float)
    df["local_id"]            = pd.to_numeric(df["local_id"],    errors="coerce").astype(float)
    df["ssid"]                = pd.to_numeric(df["ssid"],        errors="coerce").astype(float)
    df["grade"]               = pd.to_numeric(df["grade"],       errors="coerce").astype(float)
    df["day_count"]           = pd.to_numeric(df["day_count"],   errors="coerce").astype(float)
    df["membership"]          = pd.to_numeric(df["membership"],  errors="coerce")
    df["membership_multiplier"] = pd.to_numeric(df["membership_multiplier"], errors="coerce")
    df["entry_date"]          = pd.to_datetime(df["entry_date"], errors="coerce").dt.date
    df["exit_date"]           = pd.to_datetime(df["exit_date"],  errors="coerce").dt.date

    # Derived flag — 160+ days is the standard threshold for full-year enrollment
    df["enrolled_160_days"] = df["membership"] >= 160

    logger.info(
        f"Transformed {len(df)} enrollment rows — "
        f"{df['enrolled_160_days'].sum()} enrolled 160+ days"
    )

    return {"enrollment": df}
