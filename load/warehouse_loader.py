"""
Warehouse loader — writes transformed SIS and Acadience data to PostgreSQL.

SIS operations (in order):
    1. Create schemas and tables if they don't exist
    2. Append raw snapshot to staging.sis_students
    3. Upsert warehouse.dim_schools
    4. Upsert warehouse.dim_students
    5. Log the run to staging.etl_runs

Acadience operations (in order):
    1. Append raw snapshot to staging.acadience_benchmarks
    2. Upsert warehouse.fact_acadience_reading
    3. Upsert warehouse.fact_acadience_math
    4. Log the run to staging.etl_runs
"""

import logging
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import text

from utils.db import engine


def load(raw: pd.DataFrame, transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist raw and transformed SIS data to PostgreSQL.

    Args:
        raw:         Full 158-column DataFrame from the extractor
        transformed: Dict with 'students' and 'schools' keys from the transformer
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    students = transformed["students"]
    schools = transformed["schools"]

    try:
        # -------------------------------------------------------------------
        # Provision schemas and tables on first run
        # -------------------------------------------------------------------
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        # -------------------------------------------------------------------
        # 1. Staging snapshot — full raw export with timestamp
        # -------------------------------------------------------------------
        snapshot = raw.copy()
        snapshot["snapshot_at"] = started_at
        snapshot.to_sql(
            "sis_students",
            engine,
            schema="staging",
            if_exists="append",
            index=False,
        )
        logger.info(f"Saved {len(snapshot)} raw rows to staging.sis_students")

        # -------------------------------------------------------------------
        # 2. Upsert dim_schools (must run before dim_students — FK dependency)
        # -------------------------------------------------------------------
        _upsert(df=schools, table="dim_schools", schema="warehouse", pk="school_id")
        logger.info(f"Upserted {len(schools)} rows into warehouse.dim_schools")

        # -------------------------------------------------------------------
        # 3. Upsert dim_students
        # -------------------------------------------------------------------
        _upsert(df=students, table="dim_students", schema="warehouse", pk="local_id")
        logger.info(f"Upserted {len(students)} rows into warehouse.dim_students")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"SIS load failed: {exc}")
        raise

    finally:
        _log_run(
            source="sis",
            row_count=len(students),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def load_acadience_pm(raw: pd.DataFrame, transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist raw and transformed Acadience PM data to PostgreSQL.

    Args:
        raw:         Full raw DataFrame from the PM extractor
        transformed: Dict with 'pm' key from the PM transformer
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    pm = transformed["pm"]

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        # -------------------------------------------------------------------
        # 1. Upsert fact_acadience_pm
        # -------------------------------------------------------------------
        _upsert_composite(
            df=pm,
            table="fact_acadience_pm",
            schema="warehouse",
            pk=["ssid", "school_year", "assessment_date", "measure"],
        )
        logger.info(f"Upserted {len(pm)} rows into warehouse.fact_acadience_pm")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"Acadience PM load failed: {exc}")
        raise

    finally:
        _log_run(
            source="acadience_pm",
            row_count=len(pm),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def _ensure_schemas(conn) -> None:
    for schema in ("staging", "warehouse", "audit"):
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))


def load_acadience(
    raw: pd.DataFrame,
    transformed: dict[str, pd.DataFrame],
    skip_staging: bool = False,
) -> None:
    """
    Persist raw and transformed Acadience data to PostgreSQL.

    Args:
        raw:          Full raw DataFrame from the extractor
        transformed:  Dict with 'reading' and 'math' keys from the transformer
        skip_staging: If True, skip writing to staging.acadience_benchmarks.
                      Use this for historical CSV loads where the file itself
                      is the raw archive.
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    reading = transformed["reading"]
    math = transformed["math"]

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        # -------------------------------------------------------------------
        # 1. Staging snapshot — full raw export with timestamp (API runs only)
        # -------------------------------------------------------------------
        if not skip_staging:
            snapshot = raw.copy()
            snapshot["snapshot_at"] = started_at
            snapshot.to_sql(
                "acadience_benchmarks",
                engine,
                schema="staging",
                if_exists="replace",
                index=False,
            )
            logger.info(f"Saved {len(snapshot)} raw rows to staging.acadience_benchmarks")
        else:
            logger.info("Skipping staging snapshot (historical load)")

        # -------------------------------------------------------------------
        # 2. Upsert fact_acadience_reading
        # -------------------------------------------------------------------
        _upsert_composite(
            df=reading,
            table="fact_acadience_reading",
            schema="warehouse",
            pk=["ssid", "school_year", "benchmark_period"],
        )
        logger.info(f"Upserted {len(reading)} rows into warehouse.fact_acadience_reading")

        # -------------------------------------------------------------------
        # 3. Upsert fact_acadience_math
        # -------------------------------------------------------------------
        _upsert_composite(
            df=math,
            table="fact_acadience_math",
            schema="warehouse",
            pk=["ssid", "school_year", "benchmark_period"],
        )
        logger.info(f"Upserted {len(math)} rows into warehouse.fact_acadience_math")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"Acadience load failed: {exc}")
        raise

    finally:
        _log_run(
            source="acadience",
            row_count=len(reading),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def load_aspire_plus(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed Aspire Plus data to PostgreSQL.

    Load strategy: upsert by (local_id, school_year). Rows for students not
    in dim_students are filtered out. No staging snapshot — source CSVs are
    the raw archive.

    Args:
        transformed: Dict with key 'aspire_plus' from aspire_plus_transformer.transform().
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    df = transformed.get("aspire_plus", pd.DataFrame())

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        _upsert_composite(
            df=df,
            table="fact_aspire_plus",
            schema="warehouse",
            pk=["local_id", "school_year"],
        )
        logger.info(f"Upserted {len(df)} rows into warehouse.fact_aspire_plus")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"Aspire Plus load failed: {exc}")
        raise

    finally:
        _log_run(
            source="aspire_plus",
            row_count=len(df),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def load_rise(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed RISE state assessment data to PostgreSQL.

    Load strategy: upsert by (ssid, school_year, grade). Safe to rerun for
    any year without touching other years' data. Rows for students not in
    dim_students are filtered out. No staging snapshot — the source CSVs
    are the raw archive.

    Args:
        transformed: Dict with keys 'ela', 'math', 'science', 'writing'
                     from rise_transformer.transform().
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None
    total_rows = 0

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        subject_tables = {
            "ela":     "fact_rise_ela",
            "math":    "fact_rise_math",
            "science": "fact_rise_science",
            "writing": "fact_rise_writing",
        }

        for key, table in subject_tables.items():
            df = transformed.get(key)
            if df is None or df.empty:
                continue

            _upsert_composite(
                df=df,
                table=table,
                schema="warehouse",
                pk=["ssid", "school_year", "grade"],
            )
            logger.info(f"Upserted {len(df)} rows into warehouse.{table}")
            total_rows += len(df)

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"RISE load failed: {exc}")
        raise

    finally:
        _log_run(
            source="rise",
            row_count=total_rows,
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def load_attendance(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed attendance data to PostgreSQL.

    Load strategy: replace-by-school-year. For each school_year present in the
    input, existing rows are deleted and new rows inserted. This makes daily
    reruns idempotent (rerun current year, history untouched).

    Args:
        transformed: Dict with 'attendance' key — per-student-per-day DataFrame.
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    attendance = transformed["attendance"]

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        years = sorted(attendance["school_year"].unique().tolist())

        with engine.begin() as conn:
            r = conn.execute(
                text("DELETE FROM warehouse.fact_attendance_daily WHERE school_year = ANY(:years)"),
                {"years": years},
            )
            logger.info(f"Deleted {r.rowcount} existing rows for years {years}")

        attendance.to_sql(
            "fact_attendance_daily",
            engine,
            schema="warehouse",
            if_exists="append",
            index=False,
            chunksize=10000,
            method="multi",
        )
        logger.info(f"Inserted {len(attendance):,} rows into warehouse.fact_attendance_daily")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"Attendance load failed: {exc}")
        raise

    finally:
        _log_run(
            source="attendance",
            row_count=len(attendance),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def load_enrollment(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed enrollment data to PostgreSQL.

    Load strategy: replace-by-school-year. For each school_year present in
    the input, existing rows are deleted and new rows inserted. Safe to rerun.

    Args:
        transformed: Dict with 'enrollment' key from enrollment_transformer.transform().
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    df = transformed["enrollment"]

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        years = sorted(df["school_year"].dropna().unique().tolist())

        with engine.begin() as conn:
            r = conn.execute(
                text("DELETE FROM warehouse.fact_enrollment WHERE school_year = ANY(:years)"),
                {"years": [int(y) for y in years]},
            )
            logger.info(f"Deleted {r.rowcount} existing rows for years {years}")

        df.to_sql(
            "fact_enrollment",
            engine,
            schema="warehouse",
            if_exists="append",
            index=False,
            chunksize=500,
        )
        logger.info(f"Inserted {len(df):,} rows into warehouse.fact_enrollment")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"Enrollment load failed: {exc}")
        raise

    finally:
        _log_run(
            source="enrollment",
            row_count=len(df),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def _ensure_tables(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS staging.etl_runs (
            id            SERIAL PRIMARY KEY,
            source        TEXT        NOT NULL,
            row_count     INTEGER,
            status        TEXT        NOT NULL,
            error_message TEXT,
            started_at    TIMESTAMPTZ NOT NULL,
            finished_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.dim_schools (
            school_id   INTEGER PRIMARY KEY,
            school_name TEXT
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.dim_students (
            local_id                   INTEGER PRIMARY KEY,
            ssid                       NUMERIC,
            ferpa_opt_out              TEXT,
            preferred_first            TEXT,
            preferred_last             TEXT,
            legal_first                TEXT,
            legal_last                 TEXT,
            display_first              TEXT,
            display_last               TEXT,
            gender                     TEXT,
            date_of_birth              DATE,
            grade                      INTEGER,
            ethnicity                  TEXT,
            race                       TEXT,
            home_city                  TEXT,
            school_id                  INTEGER REFERENCES warehouse.dim_schools(school_id),
            entry_date                 DATE,
            exit_date                  DATE,
            exit_code                  TEXT,
            is_active                  BOOLEAN,
            economically_disadvantaged TEXT,
            iep_disability             TEXT,
            tribal_affiliation         TEXT,
            yic                        TEXT,
            ell                        TEXT,
            homeless                   NUMERIC,
            migrant                    TEXT,
            email                      TEXT,
            contact1_last              TEXT,
            contact1_first             TEXT,
            contact1_email             TEXT
        )
    """))


    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_acadience_reading (
            ssid                                BIGINT,
            school_year                         TEXT,
            benchmark_period                    TEXT,
            school_name                         TEXT,
            grade                               TEXT,
            fsf_score                           NUMERIC,
            fsf_status                          TEXT,
            fsf_national_percentile             NUMERIC,
            fsf_date                            DATE,
            lnf_score                           NUMERIC,
            lnf_national_percentile             NUMERIC,
            lnf_date                            DATE,
            psf_score                           NUMERIC,
            psf_status                          TEXT,
            psf_national_percentile             NUMERIC,
            psf_date                            DATE,
            nwf_cls_score                       NUMERIC,
            nwf_cls_status                      TEXT,
            nwf_cls_national_percentile         NUMERIC,
            nwf_wwr_score                       NUMERIC,
            nwf_wwr_status                      TEXT,
            nwf_wwr_national_percentile         NUMERIC,
            nwf_date                            DATE,
            orf_wc_score                        NUMERIC,
            orf_wc_status                       TEXT,
            orf_wc_national_percentile          NUMERIC,
            orf_accuracy_score                  NUMERIC,
            orf_accuracy_status                 TEXT,
            orf_accuracy_national_percentile    NUMERIC,
            orf_date                            DATE,
            retell_score                        NUMERIC,
            retell_status                       TEXT,
            retell_national_percentile          NUMERIC,
            retell_quality_score                NUMERIC,
            retell_quality_status               TEXT,
            maze_adjusted_score                 NUMERIC,
            maze_status                         TEXT,
            maze_national_percentile            NUMERIC,
            maze_date                           DATE,
            reading_composite_score             NUMERIC,
            reading_composite_status            TEXT,
            reading_composite_pathway           TEXT,
            reading_composite_national_percentile NUMERIC,
            reading_composite_date              DATE,
            reading_composite_class_rank        INTEGER,
            reading_composite_quartile          INTEGER,
            lexile_reading                      TEXT,
            PRIMARY KEY (ssid, school_year, benchmark_period)
        )
    """))

    conn.execute(text("""
        ALTER TABLE warehouse.fact_acadience_reading
            ADD COLUMN IF NOT EXISTS reading_composite_class_rank INTEGER,
            ADD COLUMN IF NOT EXISTS reading_composite_quartile INTEGER,
            ADD COLUMN IF NOT EXISTS fsf_date DATE,
            ADD COLUMN IF NOT EXISTS lnf_date DATE,
            ADD COLUMN IF NOT EXISTS psf_date DATE,
            ADD COLUMN IF NOT EXISTS nwf_date DATE,
            ADD COLUMN IF NOT EXISTS orf_date DATE,
            ADD COLUMN IF NOT EXISTS maze_date DATE,
            ADD COLUMN IF NOT EXISTS reading_composite_date DATE
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_acadience_math (
            ssid                                BIGINT,
            school_year                         TEXT,
            benchmark_period                    TEXT,
            school_name                         TEXT,
            grade                               TEXT,
            bqd_score                           NUMERIC,
            bqd_status                          TEXT,
            bqd_national_percentile             NUMERIC,
            bqd_date                            DATE,
            nif_score                           NUMERIC,
            nif_status                          TEXT,
            nif_national_percentile             NUMERIC,
            nif_date                            DATE,
            nnf_score                           NUMERIC,
            nnf_status                          TEXT,
            nnf_national_percentile             NUMERIC,
            nnf_date                            DATE,
            aqd_score                           NUMERIC,
            aqd_status                          TEXT,
            aqd_national_percentile             NUMERIC,
            aqd_date                            DATE,
            mnf_score                           NUMERIC,
            mnf_status                          TEXT,
            mnf_national_percentile             NUMERIC,
            mnf_date                            DATE,
            comp_score                          NUMERIC,
            comp_status                         TEXT,
            comp_national_percentile            NUMERIC,
            comp_date                           DATE,
            ca_score                            NUMERIC,
            ca_status                           TEXT,
            ca_national_percentile              NUMERIC,
            ca_date                             DATE,
            math_composite_score                NUMERIC,
            math_composite_status               TEXT,
            math_composite_pathway              TEXT,
            math_composite_national_percentile  NUMERIC,
            math_composite_date                 DATE,
            math_composite_class_rank           INTEGER,
            math_composite_quartile             INTEGER,
            PRIMARY KEY (ssid, school_year, benchmark_period)
        )
    """))

    conn.execute(text("""
        ALTER TABLE warehouse.fact_acadience_math
            ADD COLUMN IF NOT EXISTS math_composite_class_rank INTEGER,
            ADD COLUMN IF NOT EXISTS math_composite_quartile INTEGER,
            ADD COLUMN IF NOT EXISTS bqd_date DATE,
            ADD COLUMN IF NOT EXISTS nif_date DATE,
            ADD COLUMN IF NOT EXISTS nnf_date DATE,
            ADD COLUMN IF NOT EXISTS aqd_date DATE,
            ADD COLUMN IF NOT EXISTS mnf_date DATE,
            ADD COLUMN IF NOT EXISTS comp_date DATE,
            ADD COLUMN IF NOT EXISTS ca_date DATE,
            ADD COLUMN IF NOT EXISTS math_composite_date DATE
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_acadience_pm (
            ssid             BIGINT,
            school_year      TEXT,
            assessment_date  DATE,
            measure          TEXT,
            school_name      TEXT,
            grade            TEXT,
            subject          TEXT,
            monitor_level    NUMERIC,
            score            INTEGER,
            PRIMARY KEY (ssid, school_year, assessment_date, measure)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_attendance_daily (
            local_id            INTEGER NOT NULL,
            date                DATE    NOT NULL,
            school_year         INTEGER NOT NULL,
            school_id           INTEGER,
            term                SMALLINT,
            periods             INTEGER NOT NULL,
            absences            INTEGER NOT NULL,
            excused_absences    INTEGER NOT NULL,
            unexcused_absences  INTEGER NOT NULL,
            tardies             INTEGER NOT NULL,
            PRIMARY KEY (local_id, date)
        )
    """))
    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_fact_attendance_daily_year
            ON warehouse.fact_attendance_daily (school_year)
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_rise_ela (
            ssid                                    BIGINT   NOT NULL,
            school_year                             TEXT     NOT NULL,
            grade                                   SMALLINT NOT NULL,
            school_name                             TEXT,
            scale_score                             NUMERIC,
            class_rank                              INTEGER,
            quartile                                SMALLINT,
            performance                             SMALLINT,
            language_performance                    SMALLINT,
            listening_comprehension_performance     SMALLINT,
            reading_informational_text_performance  SMALLINT,
            reading_literature_performance          SMALLINT,
            PRIMARY KEY (ssid, school_year, grade)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_rise_math (
            ssid                                        BIGINT   NOT NULL,
            school_year                                 TEXT     NOT NULL,
            grade                                       SMALLINT NOT NULL,
            school_name                                 TEXT,
            scale_score                                 NUMERIC,
            class_rank                                  INTEGER,
            quartile                                    SMALLINT,
            performance                                 SMALLINT,
            measurement_data_geometry_performance       SMALLINT,
            number_operations_fractions_performance     SMALLINT,
            number_operations_base_ten_performance      SMALLINT,
            operations_algebraic_thinking_performance   SMALLINT,
            expressions_equations_performance           SMALLINT,
            geometry_stats_probability_performance      SMALLINT,
            ratios_proportional_relationships_performance SMALLINT,
            the_number_system_performance               SMALLINT,
            geometry_performance                        SMALLINT,
            statistics_probability_performance          SMALLINT,
            functions_performance                       SMALLINT,
            geometry_the_number_system_performance      SMALLINT,
            PRIMARY KEY (ssid, school_year, grade)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_rise_science (
            ssid                                            BIGINT   NOT NULL,
            school_year                                     TEXT     NOT NULL,
            grade                                           SMALLINT NOT NULL,
            school_name                                     TEXT,
            scale_score                                     NUMERIC,
            class_rank                                      INTEGER,
            quartile                                        SMALLINT,
            performance                                     SMALLINT,
            energy_transfer_performance                     SMALLINT,
            observable_patterns_sky_performance             SMALLINT,
            organisms_functioning_environment_performance   SMALLINT,
            wave_patterns_performance                       SMALLINT,
            earth_systems_characteristics_performance       SMALLINT,
            cycling_matter_ecosystems_performance           SMALLINT,
            properties_changes_matter_performance           SMALLINT,
            weather_patterns_climate_performance            SMALLINT,
            energy_affects_matter_performance               SMALLINT,
            stability_change_ecosystems_performance         SMALLINT,
            structure_motion_solar_system_performance       SMALLINT,
            changes_species_over_time_performance           SMALLINT,
            changes_earth_over_time_performance             SMALLINT,
            forces_interactions_matter_performance          SMALLINT,
            reproduction_inheritance_performance            SMALLINT,
            structure_function_life_performance             SMALLINT,
            energy_stored_transferred_performance           SMALLINT,
            interactions_natural_systems_performance        SMALLINT,
            life_systems_matter_energy_performance          SMALLINT,
            matter_energy_physical_world_performance        SMALLINT,
            PRIMARY KEY (ssid, school_year, grade)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_rise_writing (
            ssid                                    BIGINT   NOT NULL,
            school_year                             TEXT     NOT NULL,
            grade                                   SMALLINT NOT NULL,
            school_name                             TEXT,
            writing_score                           NUMERIC,
            informative_conventions                 SMALLINT,
            informative_evidence_elaboration        SMALLINT,
            informative_purpose_focus_organization  SMALLINT,
            opinion_conventions                     SMALLINT,
            opinion_evidence_elaboration            SMALLINT,
            opinion_purpose_focus_organization      SMALLINT,
            argumentative_conventions               SMALLINT,
            argumentative_evidence_elaboration      SMALLINT,
            argumentative_purpose_focus_organization SMALLINT,
            PRIMARY KEY (ssid, school_year, grade)
        )
    """))

    conn.execute(text("""
        ALTER TABLE warehouse.fact_rise_writing
            ADD COLUMN IF NOT EXISTS composition_score NUMERIC,
            ADD COLUMN IF NOT EXISTS conventions_score NUMERIC,
            ADD COLUMN IF NOT EXISTS writing_prompt_type TEXT
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_aspire_plus (
            local_id                        INTEGER  NOT NULL,
            school_year                     TEXT     NOT NULL,
            ssid                            BIGINT,
            grade                           SMALLINT,
            school_number                   INTEGER,
            composite_scale_score           NUMERIC,
            composite_class_rank            INTEGER,
            composite_quartile              SMALLINT,
            composite_predicted_act         NUMERIC,
            composite_predicted_act_low     NUMERIC,
            composite_predicted_act_high    NUMERIC,
            ela_scale_score                 NUMERIC,
            ela_class_rank                  INTEGER,
            ela_quartile                    SMALLINT,
            ela_proficiency                 NUMERIC,
            stem_scale_score                NUMERIC,
            stem_class_rank                 INTEGER,
            stem_quartile                   SMALLINT,
            stem_proficiency                NUMERIC,
            english_scale_score             NUMERIC,
            english_class_rank              INTEGER,
            english_quartile                SMALLINT,
            english_proficiency             NUMERIC,
            english_predicted_act           NUMERIC,
            english_predicted_act_low       NUMERIC,
            english_predicted_act_high      NUMERIC,
            reading_scale_score             NUMERIC,
            reading_class_rank              INTEGER,
            reading_quartile                SMALLINT,
            reading_proficiency             NUMERIC,
            reading_predicted_act           NUMERIC,
            reading_predicted_act_low       NUMERIC,
            reading_predicted_act_high      NUMERIC,
            math_scale_score                NUMERIC,
            math_class_rank                 INTEGER,
            math_quartile                   SMALLINT,
            math_proficiency                NUMERIC,
            math_predicted_act              NUMERIC,
            math_predicted_act_low          NUMERIC,
            math_predicted_act_high         NUMERIC,
            science_scale_score             NUMERIC,
            science_class_rank              INTEGER,
            science_quartile                SMALLINT,
            science_proficiency             NUMERIC,
            science_predicted_act           NUMERIC,
            science_predicted_act_low       NUMERIC,
            science_predicted_act_high      NUMERIC,
            PRIMARY KEY (local_id, school_year)
        )
    """))
    conn.execute(text("""
        ALTER TABLE warehouse.fact_aspire_plus
            ADD COLUMN IF NOT EXISTS ela_scale_score      NUMERIC,
            ADD COLUMN IF NOT EXISTS ela_class_rank       INTEGER,
            ADD COLUMN IF NOT EXISTS ela_quartile         SMALLINT,
            ADD COLUMN IF NOT EXISTS ela_proficiency      NUMERIC,
            ADD COLUMN IF NOT EXISTS english_scale_score  NUMERIC,
            ADD COLUMN IF NOT EXISTS english_class_rank   INTEGER,
            ADD COLUMN IF NOT EXISTS english_quartile     SMALLINT,
            ADD COLUMN IF NOT EXISTS english_proficiency  NUMERIC,
            ADD COLUMN IF NOT EXISTS english_predicted_act      NUMERIC,
            ADD COLUMN IF NOT EXISTS english_predicted_act_low  NUMERIC,
            ADD COLUMN IF NOT EXISTS english_predicted_act_high NUMERIC
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_toscrf (
            local_id            INTEGER  NOT NULL,
            school_year         TEXT     NOT NULL,
            assessment_window   TEXT     NOT NULL,
            school_name         TEXT,
            grade               TEXT,
            form                TEXT,
            test_date           TEXT,
            raw_score           NUMERIC,
            age                 TEXT,
            age_equivalent      TEXT,
            grade_equivalent    TEXT,
            percentile_rank     NUMERIC,
            index_score         NUMERIC,
            descriptive_term    TEXT,
            class_rank          INTEGER,
            quartile            SMALLINT,
            PRIMARY KEY (local_id, school_year, assessment_window)
        )
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.dim_homeroom (
            local_id            INTEGER  NOT NULL,
            school_year         INTEGER  NOT NULL,
            ssid                BIGINT,
            school_id           INTEGER,
            school_abbrev       TEXT,
            homeroom_course     TEXT,
            homeroom_teacher    TEXT,
            PRIMARY KEY (local_id, school_year)
        )
    """))
    # Migration: add school_year to pre-existing single-PK tables
    conn.execute(text("""
        ALTER TABLE warehouse.dim_homeroom
            ADD COLUMN IF NOT EXISTS school_year INTEGER NOT NULL DEFAULT 2026
    """))
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'dim_homeroom_pkey'
                  AND contype = 'p'
                  AND conrelid = 'warehouse.dim_homeroom'::regclass
                  AND array_length(conkey, 1) = 2
            ) THEN
                ALTER TABLE warehouse.dim_homeroom DROP CONSTRAINT IF EXISTS dim_homeroom_pkey;
                ALTER TABLE warehouse.dim_homeroom ADD PRIMARY KEY (local_id, school_year);
            END IF;
        END $$
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_wida (
            local_id            INTEGER  NOT NULL,
            school_year         TEXT     NOT NULL,
            overall             NUMERIC,
            listening           NUMERIC,
            speaking            NUMERIC,
            reading             NUMERIC,
            writing             NUMERIC,
            comprehension       NUMERIC,
            literacy            NUMERIC,
            oral                NUMERIC,
            PRIMARY KEY (local_id, school_year)
        )
    """))

    conn.execute(text("""
        ALTER TABLE warehouse.fact_wida
            DROP COLUMN IF EXISTS overall_class_rank,
            DROP COLUMN IF EXISTS overall_quartile
    """))

    # Migration: drop fact_enrollment if it has any primary key — students can
    # re-enroll at the same school mid-year, making track-based PKs non-unique.
    # Replace-by-year in load_enrollment handles idempotency; no PK needed.
    conn.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                JOIN pg_class t     ON t.oid = c.conrelid
                WHERE n.nspname = 'warehouse'
                  AND t.relname = 'fact_enrollment'
                  AND c.contype = 'p'
            ) THEN
                DROP TABLE warehouse.fact_enrollment;
            END IF;
        END $$
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_enrollment (
            local_id              INTEGER,
            school_year           INTEGER,
            track_id              INTEGER,
            ssid                  BIGINT,
            aspire_student_id     INTEGER,
            school_code           TEXT,
            school_abbrev         TEXT,
            grade                 SMALLINT,
            entry_date            DATE,
            exit_date             DATE,
            entry_code            TEXT,
            exit_code             TEXT,
            student_status        TEXT,
            is_part_time          BOOLEAN,
            residency_code        SMALLINT,
            membership_multiplier NUMERIC,
            is_projected          BOOLEAN,
            day_count             INTEGER,
            membership            NUMERIC,
            enrolled_160_days     BOOLEAN,
            row_student_year      SMALLINT,
            row_student_track     SMALLINT
        )
    """))

    conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_fact_enrollment_student_year
            ON warehouse.fact_enrollment (local_id, school_year)
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS warehouse.fact_act (
            act_id              TEXT     NOT NULL,
            test_date           TEXT     NOT NULL,
            ssid                BIGINT,
            school_year         TEXT,
            school_org_number   INTEGER,
            composite_score     SMALLINT,
            composite_class_rank INTEGER,
            composite_quartile  SMALLINT,
            english_score       SMALLINT,
            english_class_rank  INTEGER,
            english_quartile    SMALLINT,
            math_score          SMALLINT,
            math_class_rank     INTEGER,
            math_quartile       SMALLINT,
            reading_score       SMALLINT,
            reading_class_rank  INTEGER,
            reading_quartile    SMALLINT,
            science_score       SMALLINT,
            science_class_rank  INTEGER,
            science_quartile    SMALLINT,
            stem_score          SMALLINT,
            stem_class_rank     INTEGER,
            stem_quartile       SMALLINT,
            PRIMARY KEY (act_id, test_date)
        )
    """))

    # ------------------------------------------------------------------
    # Superset views — normalize benchmark + PM data for line charts.
    # Schema: (ssid, student_name, school_year, assessment_date, measure,
    #          series, score)
    # Filter by student_name + measure in Superset; series splits the two
    # lines ('Benchmark' vs 'Progress Monitoring').
    # Note: NWF CLS and NWF WWR share nwf_date; ORF, Retell, and Retell
    # Quality share orf_date — matching how Acadience records them.
    # ------------------------------------------------------------------

    conn.execute(text("""
        CREATE OR REPLACE VIEW warehouse.v_acadience_reading AS

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first AS student_name,
               r.school_year,
               r.fsf_date          AS assessment_date,
               'FSF'               AS measure,
               'Benchmark'         AS series,
               r.fsf_score         AS score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.fsf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.lnf_date, 'LNF', 'Benchmark', r.lnf_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.lnf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.psf_date, 'PSF', 'Benchmark', r.psf_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.psf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.nwf_date, 'NWF CLS', 'Benchmark', r.nwf_cls_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.nwf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.nwf_date, 'NWF WWR', 'Benchmark', r.nwf_wwr_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.nwf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.orf_date, 'ORF WC', 'Benchmark', r.orf_wc_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.orf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.orf_date, 'ORF Accuracy', 'Benchmark', r.orf_accuracy_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.orf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.orf_date, 'Retell', 'Benchmark', r.retell_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.orf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.orf_date, 'Retell Quality', 'Benchmark', r.retell_quality_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.orf_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.maze_date, 'Maze Adjusted', 'Benchmark', r.maze_adjusted_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.maze_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT r.ssid,
               s.display_last || ', ' || s.display_first,
               r.school_year, r.reading_composite_date, 'Reading Composite', 'Benchmark',
               r.reading_composite_score
        FROM warehouse.fact_acadience_reading r
        LEFT JOIN warehouse.dim_students s ON s.ssid = r.ssid::NUMERIC
        WHERE r.reading_composite_date IS NOT NULL
          AND r.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_reading)

        UNION ALL

        SELECT pm.ssid,
               s.display_last || ', ' || s.display_first,
               pm.school_year, pm.assessment_date, pm.measure,
               'Progress Monitoring', pm.score::NUMERIC
        FROM warehouse.fact_acadience_pm pm
        LEFT JOIN warehouse.dim_students s ON s.ssid = pm.ssid::NUMERIC
        WHERE pm.subject = 'reading'
          AND pm.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_pm)
    """))

    conn.execute(text("""
        CREATE OR REPLACE VIEW warehouse.v_acadience_math AS

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first AS student_name,
               m.school_year,
               m.bqd_date          AS assessment_date,
               'BQD'               AS measure,
               'Benchmark'         AS series,
               m.bqd_score         AS score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.bqd_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first,
               m.school_year, m.nif_date, 'NIF', 'Benchmark', m.nif_score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.nif_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first,
               m.school_year, m.nnf_date, 'NNF', 'Benchmark', m.nnf_score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.nnf_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first,
               m.school_year, m.aqd_date, 'AQD', 'Benchmark', m.aqd_score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.aqd_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first,
               m.school_year, m.mnf_date, 'MNF', 'Benchmark', m.mnf_score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.mnf_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first,
               m.school_year, m.comp_date, 'Comp', 'Benchmark', m.comp_score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.comp_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first,
               m.school_year, m.ca_date, 'C&A', 'Benchmark', m.ca_score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.ca_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT m.ssid,
               s.display_last || ', ' || s.display_first,
               m.school_year, m.math_composite_date, 'Math Composite', 'Benchmark',
               m.math_composite_score
        FROM warehouse.fact_acadience_math m
        LEFT JOIN warehouse.dim_students s ON s.ssid = m.ssid::NUMERIC
        WHERE m.math_composite_date IS NOT NULL
          AND m.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_math)

        UNION ALL

        SELECT pm.ssid,
               s.display_last || ', ' || s.display_first,
               pm.school_year, pm.assessment_date, pm.measure,
               'Progress Monitoring', pm.score::NUMERIC
        FROM warehouse.fact_acadience_pm pm
        LEFT JOIN warehouse.dim_students s ON s.ssid = pm.ssid::NUMERIC
        WHERE pm.subject = 'math'
          AND pm.school_year = (SELECT MAX(school_year) FROM warehouse.fact_acadience_pm)
    """))

    conn.execute(text("""
        CREATE OR REPLACE VIEW warehouse.v_students_accountability AS
        SELECT
            s.local_id,
            s.ssid,
            s.display_last,
            s.display_first,
            s.grade,
            s.school_id,
            s.race,
            CASE
                WHEN s.iep_disability IS NULL
                OR trim(s.iep_disability) = '' THEN FALSE
                ELSE TRUE
            END AS has_iep,
            CASE
                WHEN s.ell IS NULL
                OR trim(s.ell) = '' THEN FALSE
                ELSE TRUE
            END AS is_ml,
            e.school_year,
            COALESCE(e.enrolled_160_days, FALSE) AS enrolled_160_days
        FROM warehouse.dim_students s
        LEFT JOIN (
            SELECT
                local_id,
                school_code,
                school_year,
                SUM(membership) >= 160 AS enrolled_160_days
            FROM warehouse.fact_enrollment
            GROUP BY local_id, school_code, school_year
        ) e ON s.local_id = e.local_id
            AND s.school_id::TEXT = e.school_code
        WHERE s.is_active = TRUE
    """))


def load_toscrf(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed TOSCRF data to PostgreSQL.

    Load strategy: upsert by (local_id, school_year, window).

    Args:
        transformed: Dict with key 'toscrf' from toscrf_transformer.transform().
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    df = transformed.get("toscrf", pd.DataFrame())

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        _upsert_composite(
            df=df,
            table="fact_toscrf",
            schema="warehouse",
            pk=["local_id", "school_year", "assessment_window"],
        )
        logger.info(f"Upserted {len(df)} rows into warehouse.fact_toscrf")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"TOSCRF load failed: {exc}")
        raise

    finally:
        _log_run(
            source="toscrf",
            row_count=len(df),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def load_homeroom(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed homeroom data to PostgreSQL.

    Load strategy: upsert by local_id. This is a current-state snapshot —
    each run overwrites the previous homeroom assignment.

    Args:
        transformed: Dict with key 'homeroom' from homeroom_transformer.transform().
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    df = transformed.get("homeroom", pd.DataFrame())

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        _upsert_composite(df=df, table="dim_homeroom", schema="warehouse", pk=["local_id", "school_year"])
        logger.info(f"Upserted {len(df)} rows into warehouse.dim_homeroom")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"Homeroom load failed: {exc}")
        raise

    finally:
        _log_run(
            source="homeroom",
            row_count=len(df),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def load_wida(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed WIDA data to PostgreSQL.

    Load strategy: upsert by (local_id, school_year). Rows for students
    not in dim_students are filtered out before insert.

    Args:
        transformed: Dict with key 'wida' from wida_transformer.transform().
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    df = transformed.get("wida", pd.DataFrame())

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        _upsert_composite(
            df=df,
            table="fact_wida",
            schema="warehouse",
            pk=["local_id", "school_year"],
        )
        logger.info(f"Upserted {len(df)} rows into warehouse.fact_wida")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"WIDA load failed: {exc}")
        raise

    finally:
        _log_run(
            source="wida",
            row_count=len(df),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def load_act(transformed: dict[str, pd.DataFrame]) -> None:
    """
    Persist transformed ACT data to PostgreSQL.

    Load strategy: upsert by (act_id, test_date). SSID is nullable —
    rows without a crosswalk match are stored without student linkage.

    Args:
        transformed: Dict with key 'act' from act_transformer.transform().
    """
    logger = logging.getLogger(__name__)
    started_at = datetime.now(timezone.utc)
    status = "success"
    error_message = None

    df = transformed.get("act", pd.DataFrame())

    try:
        with engine.begin() as conn:
            _ensure_schemas(conn)
            _ensure_tables(conn)

        _upsert_composite(
            df=df,
            table="fact_act",
            schema="warehouse",
            pk=["act_id", "test_date"],
        )
        logger.info(f"Upserted {len(df)} rows into warehouse.fact_act")

    except Exception as exc:
        status = "failure"
        error_message = str(exc)
        logger.error(f"ACT load failed: {exc}")
        raise

    finally:
        _log_run(
            source="act",
            row_count=len(df),
            status=status,
            error_message=error_message,
            started_at=started_at,
        )


def _upsert(df: pd.DataFrame, table: str, schema: str, pk: str) -> None:
    """
    Write df to a temporary table, then INSERT ... ON CONFLICT DO UPDATE
    into the target table. Drops the temp table when done.
    """
    tmp = f"_tmp_{table}"
    df.to_sql(tmp, engine, schema="staging", if_exists="replace", index=False)

    cols = df.columns.tolist()
    update_cols = [c for c in cols if c != pk]
    col_list = ", ".join(cols)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {schema}.{table} ({col_list})
            SELECT {col_list} FROM staging."{tmp}"
            ON CONFLICT ({pk}) DO UPDATE SET {update_set}
        """))
        conn.execute(text(f'DROP TABLE IF EXISTS staging."{tmp}"'))


def _upsert_composite(
    df: pd.DataFrame, table: str, schema: str, pk: list[str]
) -> None:
    """
    Like _upsert but for tables with a composite primary key.
    """
    tmp = f"_tmp_{table}"
    df.to_sql(tmp, engine, schema="staging", if_exists="replace", index=False)

    cols = df.columns.tolist()
    update_cols = [c for c in cols if c not in pk]
    col_list = ", ".join(cols)
    pk_conflict = ", ".join(pk)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {schema}.{table} ({col_list})
            SELECT {col_list} FROM staging."{tmp}"
            ON CONFLICT ({pk_conflict}) DO UPDATE SET {update_set}
        """))
        conn.execute(text(f'DROP TABLE IF EXISTS staging."{tmp}"'))


def _log_run(
    source: str,
    row_count: int,
    status: str,
    error_message: str | None,
    started_at: datetime,
) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO staging.etl_runs
                        (source, row_count, status, error_message, started_at)
                    VALUES
                        (:source, :row_count, :status, :error_message, :started_at)
                """),
                {
                    "source": source,
                    "row_count": row_count,
                    "status": status,
                    "error_message": error_message,
                    "started_at": started_at,
                },
            )
    except Exception as log_exc:
        logging.getLogger(__name__).warning(f"Failed to write etl_runs log: {log_exc}")
