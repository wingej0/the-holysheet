"""
Homeroom transformer — formats teacher name and renames columns to snake_case.

Input:  raw DataFrame from homeroom_extractor.extract()
Output: dict with key 'homeroom'
"""

import logging

import pandas as pd


def transform(raw: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Transform raw homeroom data into a warehouse-ready DataFrame.

    Args:
        raw: DataFrame from homeroom_extractor.extract().

    Returns:
        Dict with key 'homeroom'.
    """
    logger = logging.getLogger(__name__)

    df = raw.copy()

    df["homeroom_teacher"] = df["TeacherLastName"] + ", " + df["TeacherFirstName"]

    df = df.rename(columns={"StudentID": "local_id", "SSID": "ssid"})

    df["local_id"] = pd.to_numeric(df["local_id"], errors="coerce").astype("Int64")
    df["ssid"] = pd.to_numeric(df["ssid"], errors="coerce").astype("Int64")
    df["school_id"] = pd.to_numeric(df["school_id"], errors="coerce").astype("Int64")

    df = df[["local_id", "ssid", "school_id", "school_abbrev", "homeroom_course", "homeroom_teacher"]]

    logger.info(f"Transformed {len(df)} homeroom records")
    return {"homeroom": df}
