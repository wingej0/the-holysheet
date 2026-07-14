"""
RISE transformer — standardizes column names, converts performance levels
to numeric, computes class rank and quartile within school/grade groups,
and returns one warehouse-ready DataFrame per subject.

Input:  dict[str, pd.DataFrame] from rise_extractor.extract()
Output: dict with keys 'ela', 'math', 'science', 'writing'
"""

import logging

import pandas as pd

from transform._ranking import add_rank_and_quartile

# Performance level strings → numeric (1–4). Null stored as pd.NA.
_PERFORMANCE_MAP = {
    "1 - Below Proficient": 1,
    "2 - Approaching Proficient": 2,
    "3 - Proficient": 3,
    "4 - Highly Proficient": 4,
    "Insufficient to score": pd.NA,
    "Below Standard": 1,
    "At/Near Standard": 2,
    "Above Standard": 3,
}

# Context columns shared across all subjects
_CONTEXT = {
    "Student ID": "ssid",
    "Grade": "grade",
    "Enrolled School": "school_name",
    "school_year": "school_year",
}

ELA_RENAME = {
    **_CONTEXT,
    "ELA Scale Score": "scale_score",
    "ELA Performance": "performance",
    "Language Performance": "language_performance",
    "Listening Comprehension Performance": "listening_comprehension_performance",
    "Reading Informational Text Performance": "reading_informational_text_performance",
    "Reading Literature Performance": "reading_literature_performance",
}

MATH_RENAME = {
    **_CONTEXT,
    "Math Scale Score": "scale_score",
    "Math Performance": "performance",
    # Grades 3–5
    "Measurement and Data and Geometry Performance": "measurement_data_geometry_performance",
    "Number and Operations - Fractions Performance": "number_operations_fractions_performance",
    "Number and Operations in Base Ten Performance": "number_operations_base_ten_performance",
    "Operations and Algebraic Thinking Performance": "operations_algebraic_thinking_performance",
    # Grades 6–7
    "Expressions and Equations Performance": "expressions_equations_performance",
    "Geometry/Statistics and Probability Performance": "geometry_stats_probability_performance",
    "Ratios and Proportional Relationships Performance": "ratios_proportional_relationships_performance",
    "The Number System Performance": "the_number_system_performance",
    # Grade 8
    "Geometry Performance": "geometry_performance",
    "Statistics and Probability Performance": "statistics_probability_performance",
    "Functions Performance": "functions_performance",
    "Geometry / The Number System Performance": "geometry_the_number_system_performance",
}

SCIENCE_RENAME = {
    **_CONTEXT,
    "Science Scale Score": "scale_score",
    "Science Performance": "performance",
    "Energy Transfer Performance": "energy_transfer_performance",
    "Observable Patterns in the Sky Performance": "observable_patterns_sky_performance",
    "Organisms Functioning in Their Environment Performance": "organisms_functioning_environment_performance",
    "Wave Patterns Performance": "wave_patterns_performance",
    "Characteristics and Interactions of Earth's Systems Performance": "earth_systems_characteristics_performance",
    "Cycling of Matter in Ecosystems Performance": "cycling_matter_ecosystems_performance",
    "Properties and Changes of Matter Performance": "properties_changes_matter_performance",
    "Earth's Weather Patterns and Climate Performance": "weather_patterns_climate_performance",
    "Energy Affects Matter Performance": "energy_affects_matter_performance",
    "Stability and Change in Ecosystems Performance": "stability_change_ecosystems_performance",
    "Structure and Motion within the Solar System Performance": "structure_motion_solar_system_performance",
    "Changes in Species Over Time Performance": "changes_species_over_time_performance",
    "Changes to Earth Over Time Performance": "changes_earth_over_time_performance",
    "Forces are Interactions Between Matter Performance": "forces_interactions_matter_performance",
    "Reproduction and Inheritance Performance": "reproduction_inheritance_performance",
    "Structure and Function of Life Performance": "structure_function_life_performance",
    "Energy is Stored and Transferred in Physical Systems Performance": "energy_stored_transferred_performance",
    "Interactions with Natural Systems and Resources Performance": "interactions_natural_systems_performance",
    "Life Systems Store and Transfer Matter and Energy Performance": "life_systems_matter_energy_performance",
    "Matter and Energy Interact in the Physical World Performance": "matter_energy_physical_world_performance",
}

WRITING_RENAME = {
    **_CONTEXT,
    "Writing Score": "writing_score",
    "Informative: Conventions of Standard English": "informative_conventions",
    "Informative: Evidence and Elaboration": "informative_evidence_elaboration",
    "Informative: Purpose, Focus, and Organization": "informative_purpose_focus_organization",
    "Opinion: Conventions of Standard English": "opinion_conventions",
    "Opinion: Evidence and Elaboration": "opinion_evidence_elaboration",
    "Opinion: Purpose, Focus, and Organization": "opinion_purpose_focus_organization",
    "Argumentative: Conventions of Standard English": "argumentative_conventions",
    "Argumentative: Evidence and Elaboration": "argumentative_evidence_elaboration",
    "Argumentative: Purpose, Focus, and Organization": "argumentative_purpose_focus_organization",
    # 25-26+ rubric: single Argument-or-Informative prompt scored on
    # Composition/Conventions, already coalesced by _normalize_writing_prompts.
    "composition_score": "composition_score",
    "conventions_score": "conventions_score",
    "writing_prompt_type": "writing_prompt_type",
}

# Non-numeric flags meaning "no valid score" — same idea as _PERFORMANCE_MAP's
# "Insufficient to score" but with the exact strings used in the 25-26+ files.
_WRITING_NA_FLAGS = [
    "Insufficient Text (Copied Text from the Prompt)",
    "Insufficient Text (Too Few Words)",
    "Invalidated",
]

_RANK_GROUP_COLS = ["school_year", "school_name", "grade"]


def _normalize_writing_prompts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Starting 25-26, RISE Writing dropped the old Informative/Opinion/
    Argumentative 3-dimension rubric for a single Argument-or-Informative
    prompt (each student gets one, never both) scored on two dimensions:
    Composition and Conventions. Coalesce the two mutually-exclusive prompt
    variants into one pair of columns plus a prompt-type flag, and derive
    an overall score so it lines up with older years' 'Writing Score'.
    """
    new_cols = ["Argument: Composition", "Argument: Conventions",
                "Informative: Composition", "Informative: Conventions"]
    if not any(c in df.columns for c in new_cols):
        return df

    df = df.copy()
    for col in new_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace(_WRITING_NA_FLAGS, pd.NA), errors="coerce")
        else:
            df[col] = pd.NA

    df["composition_score"] = df["Argument: Composition"].combine_first(df["Informative: Composition"])
    df["conventions_score"] = df["Argument: Conventions"].combine_first(df["Informative: Conventions"])
    df["writing_prompt_type"] = pd.NA
    df.loc[df["Argument: Composition"].notna(), "writing_prompt_type"] = "argument"
    df.loc[df["Informative: Composition"].notna(), "writing_prompt_type"] = "informative"

    derived_score = df["composition_score"] + df["conventions_score"]
    if "Writing Score" in df.columns:
        df["Writing Score"] = df["Writing Score"].combine_first(derived_score)
    else:
        df["Writing Score"] = derived_score

    return df


def _process(
    df: pd.DataFrame,
    rename_map: dict,
    score_col: str | None,
    label: str,
    logger: logging.Logger,
) -> pd.DataFrame:
    # Select only columns present in this file (subdomain columns vary by grade)
    cols_to_keep = [c for c in rename_map if c in df.columns]
    df = df[cols_to_keep].rename(columns=rename_map).copy()

    # Drop rows with no SSID or no grade — both are required for the primary key
    before = len(df)
    df = df.dropna(subset=["ssid", "grade"]).reset_index(drop=True)
    if (dropped := before - len(df)):
        logger.warning(f"{label}: dropped {dropped} rows with null SSID or grade")

    # One row per student/year/grade
    pk = ["ssid", "school_year", "grade"]
    dupes = df.duplicated(subset=pk, keep=False).sum()
    if dupes:
        logger.warning(f"{label}: {dupes} duplicate rows — keeping first per student/year/grade")
    df = df.drop_duplicates(subset=pk, keep="first").reset_index(drop=True)

    # Coerce types
    df["ssid"] = pd.to_numeric(df["ssid"], errors="coerce").astype("Int64")
    df["grade"] = pd.to_numeric(df["grade"], errors="coerce").astype("Int64")

    if score_col and score_col in df.columns:
        df[score_col] = df[score_col].replace("Insufficient to score", pd.NA)
        df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

    # Convert all performance columns to numeric
    perf_cols = [c for c in df.columns if c == "performance" or c.endswith("_performance")]
    for col in perf_cols:
        df[col] = df[col].map(lambda x: _PERFORMANCE_MAP.get(x, x) if isinstance(x, str) else x)
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Coerce remaining numeric columns (writing subscores, etc.)
    non_numeric = {"ssid", "school_year", "school_name", "grade", "writing_prompt_type"} | set(perf_cols)
    if score_col:
        non_numeric.add(score_col)
    for col in df.columns:
        if col not in non_numeric:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if score_col and score_col in df.columns:
        df = add_rank_and_quartile(df, score_col, label.lower(), _RANK_GROUP_COLS)

    logger.info(
        f"{label}: {len(df)} rows "
        f"({df['school_year'].nunique()} year(s), grades {sorted(df['grade'].dropna().unique().tolist())})"
    )
    return df


def transform(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Transform raw RISE DataFrames into warehouse-ready form.

    Args:
        raw: Dict with keys 'ela', 'math', 'science', 'writing'
             as returned by rise_extractor.extract().

    Returns:
        Dict with the same keys, each a cleaned and renamed DataFrame.
    """
    logger = logging.getLogger(__name__)
    result = {}

    if "ela" in raw:
        result["ela"] = _process(raw["ela"], ELA_RENAME, "scale_score", "ELA", logger)
    if "math" in raw:
        result["math"] = _process(raw["math"], MATH_RENAME, "scale_score", "Math", logger)
    if "science" in raw:
        result["science"] = _process(raw["science"], SCIENCE_RENAME, "scale_score", "Science", logger)
    if "writing" in raw:
        writing_raw = _normalize_writing_prompts(raw["writing"])
        result["writing"] = _process(writing_raw, WRITING_RENAME, "writing_score", "Writing", logger)

    return result
