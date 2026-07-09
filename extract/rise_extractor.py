"""
RISE extractor — reads local CSV files organized by year and subject/grade,
normalizes grade-specific column names, and returns one DataFrame per subject.
No filtering or business logic here.

Expected directory layout:
    data/rise/{year}/{subject}{grade}.csv
    e.g. data/rise/24-25/ela3.csv, data/rise/23-24/math7.csv
"""

import logging
from pathlib import Path

import pandas as pd

RISE_DATA_DIR = Path("data/rise")

# (filename, subject, full title used in column names)
FILE_MAPPINGS = [
    ("ela3.csv",     "ELA",     "ELA Grade 3"),
    ("ela4.csv",     "ELA",     "ELA Grade 4"),
    ("ela5.csv",     "ELA",     "ELA Grade 5"),
    ("ela6.csv",     "ELA",     "ELA Grade 6"),
    ("ela7.csv",     "ELA",     "ELA Grade 7"),
    ("ela8.csv",     "ELA",     "ELA Grade 8"),
    ("math3.csv",    "Math",    "Math Grade 3"),
    ("math4.csv",    "Math",    "Math Grade 4"),
    ("math5.csv",    "Math",    "Math Grade 5"),
    ("math6.csv",    "Math",    "Math Grade 6"),
    ("math7.csv",    "Math",    "Math Grade 7"),
    ("math8.csv",    "Math",    "Math Grade 8"),
    ("science4.csv", "Science", "Science Grade 4"),
    ("science5.csv", "Science", "Science Grade 5"),
    ("science6.csv", "Science", "Science Grade 6"),
    ("science7.csv", "Science", "Science Grade 7"),
    ("science8.csv", "Science", "Science Grade 8"),
    ("writing5.csv", "Writing", "Writing Grade 5"),
    ("writing8.csv", "Writing", "Writing Grade 8"),
]

SUBJECTS = ("ELA", "Math", "Science", "Writing")


class RiseExtractError(Exception):
    pass


def extract(years: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """
    Read RISE CSV files and return one concatenated DataFrame per subject.

    Args:
        years: Year strings to load (e.g. ['23-24', '24-25']).
               If None, loads all year directories found in RISE_DATA_DIR.

    Returns:
        Dict with keys 'ela', 'math', 'science', 'writing'. Each value is a
        DataFrame with all years concatenated and a 'school_year' column added.
        Missing files are skipped with a warning.

    Raises:
        RiseExtractError: If the data directory is missing, no year dirs are
            found, or a found file can't be read/parsed.
    """
    logger = logging.getLogger(__name__)

    if not RISE_DATA_DIR.exists():
        raise RiseExtractError(f"RISE data directory not found: {RISE_DATA_DIR}")

    if years is None:
        years = sorted(d.name for d in RISE_DATA_DIR.iterdir() if d.is_dir())
        if not years:
            raise RiseExtractError(f"No year directories found in {RISE_DATA_DIR}")

    subject_frames: dict[str, list[pd.DataFrame]] = {s.lower(): [] for s in SUBJECTS}

    for year in years:
        year_dir = RISE_DATA_DIR / year
        if not year_dir.exists():
            logger.warning(f"Year directory not found: {year_dir}")
            continue

        for filename, subject, title in FILE_MAPPINGS:
            csv_file = year_dir / filename
            if not csv_file.exists():
                logger.debug(f"Not found (skipping): {csv_file}")
                continue

            try:
                df = pd.read_csv(csv_file)
            except (pd.errors.ParserError, UnicodeDecodeError, OSError) as exc:
                raise RiseExtractError(f"Error reading {csv_file}: {exc}") from exc

            # Rename grade-specific columns to subject-level names so rows
            # from all grades can be concatenated into one DataFrame.
            df = df.rename(columns={
                f"Summative: {title} Scale Score": f"{subject} Scale Score",
                f"Summative: {title} Performance": f"{subject} Performance",
            })

            df["school_year"] = year
            subject_frames[subject.lower()].append(df)
            logger.info(f"Loaded {year}/{filename}: {len(df)} rows")

    result = {}
    for subject in SUBJECTS:
        key = subject.lower()
        frames = subject_frames[key]
        if frames:
            result[key] = pd.concat(frames, ignore_index=True)
            logger.info(f"Combined {len(frames)} {subject} file(s): {len(result[key])} total rows")
        else:
            logger.warning(f"No {subject} files found")

    return result
