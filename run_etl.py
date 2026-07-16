"""
Nightly ETL orchestrator — runs extract -> transform -> load for every data
source. Intended to be triggered by cron once school is in session.

Each source is isolated: a failure in one does not stop the others from
running. Every load_* function already logs its own outcome to
staging.etl_runs; this script's exit code is non-zero if any source failed,
so cron/monitoring can flag it (e.g. via cron's mail-on-error or a wrapper
that checks $?).

Usage:
    python run_etl.py
    python run_etl.py --skip sis,homeroom,attendance,enrollment,wida
        (e.g. to pause every Aspire-sourced load during an Aspire rollover)

Acadience's local-CSV historical backfill (acadience_extractor.extract_historical)
is a one-time/occasional operation, not part of the nightly run — call it
separately when there's new historical data to load.
"""

import argparse
import logging
import sys

from extract import (
    acadience_extractor,
    acadience_pm_extractor,
    act_extractor,
    aspire_plus_extractor,
    attendance_extractor,
    enrollment_extractor,
    homeroom_extractor,
    rise_extractor,
    sis_extractor,
    toscrf_extractor,
    wida_extractor,
)
from transform import (
    acadience_pm_transformer,
    acadience_transformer,
    act_transformer,
    aspire_plus_transformer,
    attendance_transformer,
    enrollment_transformer,
    homeroom_transformer,
    rise_transformer,
    sis_transformer,
    toscrf_transformer,
    wida_transformer,
)
from load import warehouse_loader as wl

logger = logging.getLogger("run_etl")

# ---------------------------------------------------------------------------
# Update these once per school year.
#
# CURRENT_SCHOOL_YEAR: integer year used by attendance/enrollment (e.g. 2026
#   for the 2025-26 school year), matching the school_year INTEGER columns
#   in warehouse.fact_attendance_daily / fact_enrollment.
#
# ACADIENCE_YEAR_CODE: string year code used by Acadience Learning Online's
#   API — see the docstrings in extract/acadience_extractor.py and
#   extract/acadience_pm_extractor.py for how ALO maps codes to school years.
#   Double-check this value before the first run of a new school year; ALO
#   may not create the new year's code until enrollment opens.
# ---------------------------------------------------------------------------
CURRENT_SCHOOL_YEAR = 2026
ACADIENCE_YEAR_CODE = "25"


def run_sis() -> None:
    raw = sis_extractor.extract()
    transformed = sis_transformer.transform(raw)
    wl.load(raw, transformed)


def run_homeroom() -> None:
    raw = homeroom_extractor.extract()
    transformed = homeroom_transformer.transform(raw)
    wl.load_homeroom(transformed)


def run_attendance() -> None:
    raw = attendance_extractor.extract(CURRENT_SCHOOL_YEAR)
    transformed = attendance_transformer.transform(raw)
    wl.load_attendance(transformed)


def run_enrollment() -> None:
    raw = enrollment_extractor.extract(CURRENT_SCHOOL_YEAR)
    transformed = enrollment_transformer.transform(raw)
    wl.load_enrollment(transformed)


def run_wida() -> None:
    raw = wida_extractor.extract()
    transformed = wida_transformer.transform(raw)
    wl.load_wida(transformed)


def run_acadience() -> None:
    raw = acadience_extractor.extract(year=ACADIENCE_YEAR_CODE)
    transformed = acadience_transformer.transform(raw)
    wl.load_acadience(raw, transformed, skip_staging=False)


def run_acadience_pm() -> None:
    raw = acadience_pm_extractor.extract(year=ACADIENCE_YEAR_CODE)
    transformed = acadience_pm_transformer.transform(raw)
    wl.load_acadience_pm(raw, transformed)


def run_act() -> None:
    raw = act_extractor.extract()
    transformed = act_transformer.transform(raw)
    wl.load_act(transformed)


def run_aspire_plus() -> None:
    raw = aspire_plus_extractor.extract()
    transformed = aspire_plus_transformer.transform(raw)
    wl.load_aspire_plus(transformed)


def run_rise() -> None:
    raw = rise_extractor.extract()
    transformed = rise_transformer.transform(raw)
    wl.load_rise(transformed)


def run_toscrf() -> None:
    raw = toscrf_extractor.extract()
    transformed = toscrf_transformer.transform(raw)
    wl.load_toscrf(transformed)


# Order matters only for readability here — each load_* call provisions its
# own schemas/tables and there are no cross-source dependencies at run time.
SOURCES = {
    "sis": run_sis,
    "homeroom": run_homeroom,
    "attendance": run_attendance,
    "enrollment": run_enrollment,
    "wida": run_wida,
    "acadience": run_acadience,
    "acadience_pm": run_acadience_pm,
    "act": run_act,
    "aspire_plus": run_aspire_plus,
    "rise": run_rise,
    "toscrf": run_toscrf,
}


def _run_source(name: str, fn) -> bool:
    logger.info(f"=== {name}: starting ===")
    try:
        fn()
        logger.info(f"=== {name}: succeeded ===")
        return True
    except Exception:
        logger.exception(f"=== {name}: FAILED ===")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip",
        default="",
        help="Comma-separated source names to skip, e.g. "
        "'sis,homeroom,attendance,enrollment,wida'",
    )
    args = parser.parse_args()

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    unknown = skip - SOURCES.keys()
    if unknown:
        parser.error(f"Unknown source(s) in --skip: {', '.join(sorted(unknown))}")

    results = {}
    for name, fn in SOURCES.items():
        if name in skip:
            logger.info(f"=== {name}: skipped ===")
            continue
        results[name] = _run_source(name, fn)

    failed = [name for name, ok in results.items() if not ok]
    if failed:
        logger.error(f"ETL run finished with failures: {', '.join(failed)}")
        sys.exit(1)

    logger.info("ETL run finished successfully for all sources.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
