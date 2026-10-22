"""
Accountability extractor — reads USBE school-accountability Excel exports
from data/accountability/.

USBE has changed its school-accountability scoring system several times over
the years (letter grades, SFAR, PACE, ESSA 1-5 ratings, early CSI/TSI point
scales). Starting with the 2021-22 school year, USBE settled on the current
225.01-point scale (Achievement 56 / Growth 56 / Lowest Quartile 25 /
EL Progress 13 / Grad Rate 25 / ACT 25 / Advanced Coursework 25) — that's
what this extractor covers. Years before 2021-22 use incompatible schemas
and are out of scope.

Scoped to San Juan School District (USBE LEA ID 880) only: district rank
only ever needs San Juan's own schools, and the statewide rank is already a
precomputed number in each year's rank-list file, so there's no need to
pull in the other ~950 statewide schools' rows.

Filenames/sheet names are not a predictable pattern across years (USBE
renames its exports each year), so each year's sources are listed
explicitly in YEAR_SOURCES below.
"""

import logging
from pathlib import Path

import pandas as pd

ACCOUNTABILITY_DATA_DIR = Path("data/accountability")
HOME_LEA_ID = 880  # San Juan School District

# School-group breakdown files use 'LEAID' (2023-24+) or 'DistrictID'
# (2021-22, 2022-23) to identify the district. Rank-list files always use
# 'DistrictID'. TSI/ATSI files always use 'LEA ID'.
_STUDENT_GROUP_LEA_COLUMNS = ("LEAID", "DistrictID")

YEAR_SOURCES = {
    2022: {
        "student_groups": (
            "AccountabilityTSI2021.xlsx",
            "TSI Student Group Scores - 2022",
        ),
        "rank_list": ("AccountabilityRankList2021.xlsx", "School Report Card - 2022"),
    },
    2023: {
        "student_groups": (
            "AccountabilityTSI2022StudentGroup.xlsx",
            "All Group Accountability Scores",
        ),
        "rank_list": ("Accountability2022RankList.xlsx", "School Report Card"),
    },
    2024: {
        "student_groups": ("23_StudentGroupAccountability.xlsx", "Student Groups"),
        "tsi": ("23_StudentGroupAccountability.xlsx", "TSI"),
        "atsi": ("23_StudentGroupAccountability.xlsx", "ATSI"),
        "tsi_exit": ("23_StudentGroupAccountability.xlsx", "TSI Exit"),
        "atsi_exit": ("23_StudentGroupAccountability.xlsx", "ATSI Exit"),
        "csi": ("23CSI.xlsx", "Low Performing Student Groups"),
        "csi_exit": ("23CSI.xlsx", "CSI Exit"),
        "rank_list": ("23_ RankList.xlsx", "All Schools Rank List"),
    },
    2025: {
        "student_groups": ("24StudentGroupAccountability.xlsx", "Student Groups"),
        "tsi": ("24StudentGroupAccountability.xlsx", "TSI"),
        "atsi": ("24StudentGroupAccountability.xlsx", "ATSI"),
        "tsi_exit": ("24StudentGroupAccountability.xlsx", "TSI Exit"),
        "atsi_exit": ("24StudentGroupAccountability.xlsx", "ATSI Exit"),
        "csi": ("24CSI.xlsx", "Low Performing Student Groups"),
        "csi_exit": ("24CSI.xlsx", "CSI Exit"),
        "rank_list": ("24RankList.xlsx", "All Schools Rank List"),
    },
}


class AccountabilityExtractError(Exception):
    pass


def _read_sheet(fname: str, sheet: str) -> pd.DataFrame:
    path = ACCOUNTABILITY_DATA_DIR / fname
    if not path.exists():
        raise AccountabilityExtractError(f"Accountability file not found: {path}")
    return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")


def _filter_student_groups(df: pd.DataFrame) -> pd.DataFrame:
    for col in _STUDENT_GROUP_LEA_COLUMNS:
        if col in df.columns:
            return df[df[col] == HOME_LEA_ID].copy()
    raise AccountabilityExtractError(
        f"No LEA identifier column found among {list(df.columns)}"
    )


def extract() -> dict[int, dict]:
    """
    Read each configured school year's student-group, TSI/ATSI, and
    rank-list sheets, filtered to San Juan School District.

    Returns:
        Dict keyed by school_year (ending calendar year, e.g. 2025 for
        2024-25), each holding:
            'student_groups' — raw student-group rows for San Juan District
            'student_groups_statewide' — raw student-group rows for every
                                 school in the state that year (used for
                                 comparable-schools subgroup breakdowns)
            'tsi' / 'atsi'    — raw rows for groups currently identified as
                                 TSI/ATSI, for San Juan District (only
                                 present for years with separate TSI/ATSI
                                 sheets — 2024 and 2025)
            'tsi_exit' / 'atsi_exit' — raw rows for groups that exited
                                 TSI/ATSI that year, for San Juan District
                                 (same year coverage as 'tsi'/'atsi')
            'csi' / 'csi_exit' — raw rows for groups currently identified
                                 as, or that exited, CSI - Low Performing
                                 Student Groups that year, for San Juan
                                 District (same year coverage as 'tsi')
            'rank_list'       — raw school-level rank rows for San Juan
                                 District
            'rank_list_statewide' — raw school-level rank rows for every
                                 school in the state that year (used for
                                 comparable-schools matching, which needs
                                 schools outside San Juan District)
            'total_ranked'    — count of all schools ranked statewide that
                                 year (the USBE Rank denominator)

    Raises:
        AccountabilityExtractError: If the data directory or a configured
            file is missing.
    """
    logger = logging.getLogger(__name__)

    if not ACCOUNTABILITY_DATA_DIR.exists():
        raise AccountabilityExtractError(
            f"Accountability data directory not found: {ACCOUNTABILITY_DATA_DIR}"
        )

    results: dict[int, dict] = {}

    for school_year, sources in YEAR_SOURCES.items():
        year_data: dict = {}

        sg_file, sg_sheet = sources["student_groups"]
        student_groups_raw = _read_sheet(sg_file, sg_sheet)
        year_data["student_groups"] = _filter_student_groups(student_groups_raw)
        # Kept unfiltered (statewide) so comparable-schools peers (which are
        # outside San Juan District) can get the same subgroup point
        # breakdown San Juan's own schools get.
        year_data["student_groups_statewide"] = student_groups_raw
        logger.info(
            f"{school_year}: {len(year_data['student_groups'])} San Juan "
            f"student-group rows from {sg_file}"
        )

        # TSI/ATSI/CSI sheets cover groups currently identified; the *_exit
        # sheets cover groups that exited that year — a group that exits
        # mid-report is dropped from the TSI/ATSI/CSI sheet, so its
        # ExitTarget is only recoverable from the *_exit sheet. CSI (Low
        # Performing Student Groups) exit targets live in a separate file
        # from TSI/ATSI (23CSI.xlsx / 24CSI.xlsx), not the
        # StudentGroupAccountability files.
        for key in ("tsi", "atsi", "tsi_exit", "atsi_exit", "csi", "csi_exit"):
            if key in sources:
                fname, sheet = sources[key]
                df = _read_sheet(fname, sheet)
                year_data[key] = df[df["LEA ID"] == HOME_LEA_ID].copy()

        rank_file, rank_sheet = sources["rank_list"]
        rank_list = _read_sheet(rank_file, rank_sheet)
        year_data["total_ranked"] = len(rank_list)
        year_data["rank_list"] = rank_list[rank_list["DistrictID"] == HOME_LEA_ID].copy()
        # Kept unfiltered (statewide) for comparable-schools matching, which
        # by definition needs schools outside San Juan District.
        year_data["rank_list_statewide"] = rank_list
        logger.info(
            f"{school_year}: {len(year_data['rank_list'])} San Juan rank "
            f"rows out of {year_data['total_ranked']} statewide, from {rank_file}"
        )

        results[school_year] = year_data

    return results
