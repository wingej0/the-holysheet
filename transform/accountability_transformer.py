"""
Accountability transformer — normalizes the raw per-year USBE sheets from
accountability_extractor.extract() into two canonical DataFrames.

USBE renamed columns almost every year (e.g. 'AchievementPoints (56 Points)'
vs 'Achievement Points (56 Points)', 'DistrictID' vs 'LEAID') even while
keeping the same underlying 225.01-point scoring system, so each of the 4
years gets its own normalization function below. `status` values are passed
through largely as-is from the source (values differ slightly year to year —
e.g. 2021-22 only ever has 'TSI'/None since that source has no CSI/ATSI
columns at the subgroup level; 2022-23 includes 'Exited ATSI' as a distinct
value) — this reflects what USBE actually published each year, not a bug.

`exit_target` for 2022-23 is filled from that year's '2023 5% Cut Score'
column, which is the closest available substitute — USBE's own ExitTarget
figure for that specific year isn't broken out at the subgroup level in
that file the way it is in 2023-24/2024-25's dedicated TSI/ATSI sheets.
"""

import numpy as np
import pandas as pd

HOME_LEA_ID = 880  # San Juan School District

STUDENT_GROUP_COLUMNS = [
    "school_year",
    "school_id",
    "school_number",
    "school_name",
    "school_type",
    "student_group_code",
    "status",
    "year_identified",
    "exit_description",
    "exit_year",
    "exit_target",
    "achievement_points",
    "growth_points",
    "lq_points",
    "el_points",
    "grad_points",
    "act_points",
    "adv_points",
    "total_indicators",
    "total_score",
    "total_possible",
    "overall_total_percent",
]

SCHOOL_RANK_COLUMNS = [
    "school_year",
    "school_id",
    "school_number",
    "school_name",
    "school_type",
    "total_enrollment",
    "total_score",
    "total_possible",
    "overall_total_percent",
    "ranking",
    "total_ranked_statewide",
]

STATEWIDE_RANK_COLUMNS = [
    "school_year",
    "school_id",
    "school_number",
    "school_name",
    "lea_id",
    "lea_name",
    "school_type",
    "is_title_i",
    "total_enrollment",
    "overall_total_percent",
    "ranking",
]

COMPARABLE_SCHOOL_COLUMNS = [
    "school_year",
    "school_id",
    "school_name",
    "student_group_code",
    "peer_rank",
    "peer_school_id",
    "peer_school_name",
    "peer_lea_name",
    "peer_school_type",
    "peer_total_enrollment",
    "peer_status",
    "peer_achievement_points",
    "peer_growth_points",
    "peer_lq_points",
    "peer_el_points",
    "peer_grad_points",
    "peer_act_points",
    "peer_adv_points",
    "peer_total_score",
    "peer_total_possible",
    "peer_overall_total_percent",
    "match_distance",
]

N_COMPARABLE_SCHOOLS = 5


def _exit_target_lookup(*sheets: pd.DataFrame) -> dict:
    """
    Build a (school_id, student_group_code) -> exit_target lookup from the
    TSI/ATSI sheets (currently-identified groups) and, as a fallback, the
    TSI Exit/ATSI Exit sheets (groups that exited that year — USBE drops
    these from the TSI/ATSI sheet once they exit, so that's the only place
    their ExitTarget survives). Pass TSI/ATSI sheets first so they win on
    key collisions, though in practice a group is never in both a
    currently-identified sheet and its own exit sheet in the same year.
    """
    lookup = {}
    for df in sheets:
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            key = (int(row["SchoolID"]), row["StudentGroupsCode"])
            lookup.setdefault(key, row["ExitTarget"])
    return lookup


def _normalize_2022(student_groups: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame()
    df["school_year"] = student_groups["SchoolYear"]
    df["school_id"] = student_groups["SchoolID"]
    df["school_number"] = student_groups["SchoolNumber"]
    df["school_name"] = student_groups["SchoolName"]
    df["school_type"] = student_groups["SchoolType"]
    df["student_group_code"] = student_groups["StudentGroupsCode"]
    df["status"] = np.where(
        student_groups["Student Group Is TSI"] == "Yes", "TSI", None
    )
    df["year_identified"] = student_groups["FirstYearTSI"]
    df["exit_description"] = None
    df["exit_year"] = None
    df["exit_target"] = None
    df["achievement_points"] = student_groups["AchievementPoints (56 Points)"]
    df["growth_points"] = student_groups["GrowthPoints (56 Points)"]
    df["lq_points"] = student_groups["LQPoints (25 Points)"]
    df["el_points"] = student_groups["ELPoints (13 Points)"]
    df["grad_points"] = student_groups["GRPoints (25 Points)"]
    df["act_points"] = student_groups["ACTPoints (25 Points)"]
    df["adv_points"] = student_groups["AdvPoints (25 Points)"]
    df["total_indicators"] = student_groups["IndicatorCount"]
    df["total_score"] = student_groups["Total Received Points Earned"]
    df["total_possible"] = student_groups["TotalPointsPossible"]
    df["overall_total_percent"] = student_groups["TSIScore"]
    return df[STUDENT_GROUP_COLUMNS]


def _normalize_2023(student_groups: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame()
    df["school_year"] = student_groups["SchoolYear"]
    df["school_id"] = student_groups["SchoolID"]
    df["school_number"] = student_groups["SchoolNumber"]
    df["school_name"] = student_groups["SchoolName"]
    df["school_type"] = student_groups["SchoolType"]
    df["student_group_code"] = student_groups["StudentGroupsCode"]
    df["status"] = student_groups["SchoolImprovementStatus"]
    df["year_identified"] = student_groups["FirstYearATSI"].where(
        student_groups["FirstYearATSI"].notna(), student_groups["FirstYearTSI"]
    )
    df["exit_description"] = student_groups["ExitDescription"]
    df["exit_year"] = None
    df["exit_target"] = student_groups["2023 5% Cut Score"]
    df["achievement_points"] = student_groups["AchievementPoints (56 Points)"]
    df["growth_points"] = student_groups["GrowthPoints (56 Points)"]
    df["lq_points"] = student_groups["LQPoints (25 Points)"]
    df["el_points"] = student_groups["ELPoints (13 Points)"]
    df["grad_points"] = student_groups["GRPoints (25 Points)"]
    df["act_points"] = student_groups["ACTPoints (25 Points)"]
    df["adv_points"] = student_groups["AdvPoints (25 Points)"]
    df["total_indicators"] = student_groups["IndicatorCount"]
    df["total_score"] = student_groups["TotalPointsEarned"]
    df["total_possible"] = student_groups["TotalPointsPossible"]
    df["overall_total_percent"] = student_groups["AccountabilityScore"]
    return df[STUDENT_GROUP_COLUMNS]


def _normalize_modern(
    student_groups: pd.DataFrame,
    tsi: pd.DataFrame,
    atsi: pd.DataFrame,
    tsi_exit: pd.DataFrame,
    atsi_exit: pd.DataFrame,
    csi: pd.DataFrame,
    csi_exit: pd.DataFrame,
) -> pd.DataFrame:
    """Shared normalizer for 2023-24 onward, whose 'Student Groups' /
    'TSI' / 'ATSI' / 'TSI Exit' / 'ATSI Exit' sheets share an identical
    schema. CSI (Low Performing Student Groups) exit targets come from a
    separate file (e.g. 24CSI.xlsx) but the same 'ExitTarget'
    column shape, so they fold into the same lookup."""
    exit_targets = _exit_target_lookup(tsi, atsi, tsi_exit, atsi_exit, csi, csi_exit)

    df = pd.DataFrame()
    df["school_year"] = student_groups["SchoolYear"]
    df["school_id"] = student_groups["SchoolID"]
    df["school_number"] = student_groups["SchoolNumber"]
    df["school_name"] = student_groups["SchoolName"]
    df["school_type"] = student_groups["SchoolType"]
    df["student_group_code"] = student_groups["StudentGroupsCode"]
    df["status"] = student_groups["Type"]
    df["year_identified"] = student_groups["YearIdentified"]
    df["exit_description"] = student_groups["ExitDescription"]
    df["exit_year"] = student_groups["ExitYear"]
    df["exit_target"] = [
        exit_targets.get((int(sid), code))
        for sid, code in zip(student_groups["SchoolID"], student_groups["StudentGroupsCode"])
    ]
    df["achievement_points"] = student_groups["Achievement Points (56 Points)"]
    df["growth_points"] = student_groups["Growth Points (56 Points)"]
    df["lq_points"] = student_groups["Lowest Quartile Points (25 Points)"]
    df["el_points"] = student_groups["EL Progress Points (13 Points)"]
    df["grad_points"] = student_groups["Graduation Rate Points (25 Points)"]
    df["act_points"] = student_groups["ACT Points (25 Points)"]
    df["adv_points"] = student_groups["Advanced Coursework Points (25 Points)"]
    df["total_indicators"] = student_groups["TotalIndicators"]
    df["total_score"] = student_groups["TotalScore"]
    df["total_possible"] = student_groups["TotalPossible"]
    df["overall_total_percent"] = student_groups["OverallTotalPercent"]
    return df[STUDENT_GROUP_COLUMNS]


def _clean_year_cell(value):
    """
    Normalize year_identified/exit_year values, which arrive as a mix of
    ints, floats (e.g. 2022.0), strings (e.g. '2024'), and whitespace-only
    strings USBE uses in place of a true blank (e.g. FirstYearATSI=' ' when
    a group was never ATSI-identified).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _clean_text_cell(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _normalize_rank_list(rank_list: pd.DataFrame, school_year: int, total_ranked: int) -> pd.DataFrame:
    df = pd.DataFrame()
    df["school_year"] = pd.Series([school_year] * len(rank_list), index=rank_list.index)
    df["school_id"] = rank_list["SchoolID"]
    df["school_number"] = rank_list["SchoolNumber"]
    df["school_name"] = rank_list["SchoolName"]
    df["school_type"] = rank_list["SchoolType"]
    df["total_enrollment"] = rank_list["TotalEnrollment"]
    df["total_score"] = rank_list["TotalScore"]
    df["total_possible"] = rank_list["TotalPossible"]
    df["overall_total_percent"] = rank_list["OverallTotalPercent"]
    df["ranking"] = rank_list["RANKING"]
    df["total_ranked_statewide"] = total_ranked
    return df[SCHOOL_RANK_COLUMNS]


def _normalize_rank_list_statewide(rank_list_statewide: pd.DataFrame, school_year: int) -> pd.DataFrame:
    df = pd.DataFrame()
    df["school_year"] = pd.Series(
        [school_year] * len(rank_list_statewide), index=rank_list_statewide.index
    )
    df["school_id"] = rank_list_statewide["SchoolID"]
    df["school_number"] = rank_list_statewide["SchoolNumber"]
    df["school_name"] = rank_list_statewide["SchoolName"]
    df["lea_id"] = rank_list_statewide["DistrictID"]
    df["lea_name"] = rank_list_statewide["District"]
    df["school_type"] = rank_list_statewide["SchoolType"]
    df["is_title_i"] = rank_list_statewide["IsTitleISchool"]
    df["total_enrollment"] = pd.to_numeric(
        rank_list_statewide["TotalEnrollment"], errors="coerce"
    )
    df["overall_total_percent"] = pd.to_numeric(
        rank_list_statewide["OverallTotalPercent"], errors="coerce"
    )
    df["ranking"] = pd.to_numeric(rank_list_statewide["RANKING"], errors="coerce")
    return df[STATEWIDE_RANK_COLUMNS]


def _compute_comparable_schools(
    student_groups: pd.DataFrame,
    statewide_student_groups: pd.DataFrame,
    statewide_rank: pd.DataFrame,
) -> pd.DataFrame:
    """
    For each San Juan District (school_year, school, student_group_code)
    row, find the N_COMPARABLE_SCHOOLS closest statewide schools that ALSO
    report that same student group that year — not just similarly-sized
    schools in general. Subgroup composition (e.g. American Indian/Alaska
    Native enrollment) is geographically concentrated in Utah, so matching
    at the whole-school level alone can surface "similar" schools that
    don't actually serve that subgroup — USBE won't have published a score
    for a group too small to report, so there'd be nothing to compare.
    Requiring the peer to report the same group first fixes that.

    Matching:
      - hard filters: same school_year, same student_group_code, same
        school_type (E/H), same is_title_i status, excluding the reference
        school itself
      - soft ranking: combined distance on total_enrollment (school-level —
        we don't have subgroup-level enrollment/N-size to match on more
        precisely) and that group's own overall_total_percent, each
        normalized by the candidate pool's standard deviation so the two
        scales (student counts vs. score fractions) contribute comparably

    The matched peer rows already carry the full points breakdown, so this
    doubles as the "comparable schools" points table — no separate join
    needed downstream.
    """
    school_attrs = statewide_rank[
        ["school_year", "school_id", "lea_name", "is_title_i", "total_enrollment"]
    ].drop_duplicates(subset=["school_year", "school_id"], keep="first")

    # A handful of multi-site/online charter schools have duplicate
    # (SchoolID, StudentGroupsCode) rows in USBE's statewide export (see
    # accountability_transformer module notes elsewhere) — keep the first
    # so a quirky school can't occupy two of the five peer slots.
    candidates = statewide_student_groups.merge(
        school_attrs, on=["school_year", "school_id"], how="inner"
    ).drop_duplicates(subset=["school_year", "school_id", "student_group_code"], keep="first")

    references = student_groups.merge(school_attrs, on=["school_year", "school_id"], how="left")

    rows = []

    for _, ref in references.iterrows():
        if pd.isna(ref["total_enrollment"]) or pd.isna(ref["overall_total_percent"]) or pd.isna(
            ref["is_title_i"]
        ):
            continue

        pool = candidates[
            (candidates["school_year"] == ref["school_year"])
            & (candidates["student_group_code"] == ref["student_group_code"])
            & (candidates["school_type"] == ref["school_type"])
            & (candidates["is_title_i"] == ref["is_title_i"])
            & (candidates["school_id"] != ref["school_id"])
        ].dropna(subset=["total_enrollment", "overall_total_percent"])

        if pool.empty:
            continue

        enrollment_scale = pool["total_enrollment"].std() or 1
        score_scale = pool["overall_total_percent"].std() or 1

        distance = (
            (pool["total_enrollment"] - ref["total_enrollment"]).abs() / enrollment_scale
            + (pool["overall_total_percent"] - ref["overall_total_percent"]).abs() / score_scale
        )

        nearest = pool.assign(match_distance=distance).nsmallest(
            N_COMPARABLE_SCHOOLS, "match_distance"
        )

        for peer_rank, (_, peer) in enumerate(nearest.iterrows(), start=1):
            rows.append(
                {
                    "school_year": ref["school_year"],
                    "school_id": ref["school_id"],
                    "school_name": ref["school_name"],
                    "student_group_code": ref["student_group_code"],
                    "peer_rank": peer_rank,
                    "peer_school_id": peer["school_id"],
                    "peer_school_name": peer["school_name"],
                    "peer_lea_name": peer["lea_name"],
                    "peer_school_type": peer["school_type"],
                    "peer_total_enrollment": peer["total_enrollment"],
                    "peer_status": peer["status"],
                    "peer_achievement_points": peer["achievement_points"],
                    "peer_growth_points": peer["growth_points"],
                    "peer_lq_points": peer["lq_points"],
                    "peer_el_points": peer["el_points"],
                    "peer_grad_points": peer["grad_points"],
                    "peer_act_points": peer["act_points"],
                    "peer_adv_points": peer["adv_points"],
                    "peer_total_score": peer["total_score"],
                    "peer_total_possible": peer["total_possible"],
                    "peer_overall_total_percent": peer["overall_total_percent"],
                    "match_distance": round(peer["match_distance"], 4),
                }
            )

    return pd.DataFrame(rows, columns=COMPARABLE_SCHOOL_COLUMNS)


def _normalize_student_groups(school_year: int, year_data: dict, key: str) -> pd.DataFrame:
    """
    Dispatch to the right per-year normalizer for whichever student-groups
    frame is requested via `key` ('student_groups' for the San
    Juan-filtered rows, 'student_groups_statewide' for every school that
    year). The TSI/ATSI/CSI exit-target sheets used for 2024 onward are
    always San Juan-filtered regardless of `key` — harmless for statewide
    rows, since a peer school's SchoolID just won't match anything in a
    San Juan-only sheet, leaving that peer's exit_target null (status,
    year_identified, and exit_description come straight from the main
    Student Groups sheet either way, so those are populated for peers too).
    """
    student_groups = year_data[key]
    if school_year == 2022:
        return _normalize_2022(student_groups)
    if school_year == 2023:
        return _normalize_2023(student_groups)
    if school_year >= 2024:
        return _normalize_modern(
            student_groups,
            year_data.get("tsi", pd.DataFrame()),
            year_data.get("atsi", pd.DataFrame()),
            year_data.get("tsi_exit", pd.DataFrame()),
            year_data.get("atsi_exit", pd.DataFrame()),
            year_data.get("csi", pd.DataFrame()),
            year_data.get("csi_exit", pd.DataFrame()),
        )
    raise ValueError(f"No normalizer registered for school year {school_year}")


def _clean_student_groups(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["status"] = df["status"].apply(_clean_text_cell)
    df["exit_description"] = df["exit_description"].apply(_clean_text_cell)
    df["year_identified"] = df["year_identified"].apply(_clean_year_cell)
    df["exit_year"] = df["exit_year"].apply(_clean_year_cell)
    df["exit_target"] = pd.to_numeric(df["exit_target"], errors="coerce")
    return df


def transform(raw: dict[int, dict]) -> dict[str, pd.DataFrame]:
    """
    Normalize accountability_extractor.extract()'s output into canonical
    DataFrames spanning all configured years.

    Args:
        raw: Dict keyed by school_year, as returned by
            accountability_extractor.extract().

    Returns:
        Dict with keys 'student_groups', 'school_rank', and
        'comparable_schools' (peer schools matched per subgroup, including
        their full points breakdown).
    """
    student_group_frames = []
    statewide_student_group_frames = []
    rank_frames = []
    statewide_rank_frames = []

    for school_year, year_data in raw.items():
        student_group_frames.append(
            _normalize_student_groups(school_year, year_data, "student_groups")
        )
        statewide_student_group_frames.append(
            _normalize_student_groups(school_year, year_data, "student_groups_statewide")
        )
        rank_frames.append(
            _normalize_rank_list(
                year_data["rank_list"], school_year, year_data["total_ranked"]
            )
        )
        statewide_rank_frames.append(
            _normalize_rank_list_statewide(year_data["rank_list_statewide"], school_year)
        )

    student_groups = _clean_student_groups(pd.concat(student_group_frames, ignore_index=True))
    statewide_student_groups = _clean_student_groups(
        pd.concat(statewide_student_group_frames, ignore_index=True)
    )
    school_rank = pd.concat(rank_frames, ignore_index=True)
    statewide_rank = pd.concat(statewide_rank_frames, ignore_index=True)
    comparable_schools = _compute_comparable_schools(
        student_groups, statewide_student_groups, statewide_rank
    )

    return {
        "student_groups": student_groups,
        "school_rank": school_rank,
        "comparable_schools": comparable_schools,
    }
