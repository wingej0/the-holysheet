<p align="center">
  <img src="assets/holysheet_logo.jpeg" alt="the-holysheet logo: a spreadsheet with a halo and an upward trend arrow" width="240">
</p>

<p align="center">
  <a href="https://github.com/wingej0/the-holysheet/commits/main"><img src="https://img.shields.io/github/last-commit/wingej0/the-holysheet" alt="Last commit"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/wingej0/the-holysheet" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/PostgreSQL-warehouse-336791?logo=postgresql&logoColor=white" alt="PostgreSQL">
</p>

# The Holysheet

A nightly ETL pipeline that pulls student, enrollment, attendance, and assessment data out of the systems a Utah school district already uses and loads it into one PostgreSQL data warehouse. Once the data is in the warehouse, dashboards (we use Apache Superset) can join assessments to demographics, enrollment, and homerooms without anyone exporting and merging spreadsheets by hand.

It was built for **San Juan School District**. Most of the pipeline is generic for Utah districts on **Aspire SIS** and **Acadience Learning Online**, but some of it is specific to San Juan. [Adapting it for your district](#adapting-it-for-your-district) lists every place you'll need to change.

> **Student privacy:** this pipeline handles FERPA-protected student records. The repository holds **only code**. Credentials (`.env`) and source files (`data/`) are git-ignored and must never be committed. Run the pipeline on a district-controlled server, and limit access to the warehouse the same way you'd limit access to the SIS.

---

## Contents

- [How it works](#how-it-works)
- [Data sources](#data-sources)
- [What ends up in the warehouse](#what-ends-up-in-the-warehouse)
- [Setup](#setup)
- [Running it](#running-it)
- [Once-a-year maintenance](#once-a-year-maintenance)
- [Adapting it for your district](#adapting-it-for-your-district)
- [Adding a new data source](#adding-a-new-data-source)
- [Troubleshooting](#troubleshooting)

---

## How it works

Every data source goes through the same three steps, and each step has its own folder:

```
 extract/                 transform/                 load/
 ─────────                ──────────                 ─────
 Pull raw data from   →   Rename columns, fix    →   Write to PostgreSQL
 an API, database,        types, drop bad rows,      (create tables if
 Google Sheet, or         compute class rank /       missing, upsert rows,
 local CSV/Excel file     quartile, etc.             log the run)
```

- **`extract/<source>_extractor.py`**: an `extract()` function that returns raw data as a pandas DataFrame and changes nothing.
- **`transform/<source>_transformer.py`**: a `transform(raw)` function that returns a dict of clean DataFrames, one for each warehouse table.
- **`load/warehouse_loader.py`**: one `load_<source>()` function for each source. It also holds every `CREATE TABLE` statement and the reporting views.
- **`run_etl.py`**: the orchestrator. It runs every source in turn. **If one source fails, the others still run.** The script exits non-zero when anything failed, so cron or your monitoring can alert you.
- **`config/settings.py`**: reads credentials from `.env` and builds the URLs and connection strings for each source system.

### Warehouse layout

The pipeline creates three PostgreSQL schemas on its first run:

| Schema      | Purpose |
|-------------|---------|
| `warehouse` | Clean, report-ready tables (`dim_*` and `fact_*`) and views (`v_*`). **Dashboards should point here.** |
| `staging`   | Raw snapshots of some exports, plus `staging.etl_runs`, which logs the start time, row count, status, and any error for every load. |
| `audit`     | Reserved for future use. |

The pipeline never asks you to run a migration script. Every load calls `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, so an empty database is set up automatically the first time the pipeline runs.

### How rows are written

| Strategy | Used by | Behavior |
|---|---|---|
| **Upsert** (insert, or update on a primary-key match) | Most sources | Safe to rerun. History is kept, and changed rows are updated in place. |
| **Replace by school year** | Attendance, Enrollment | Deletes the current year's rows and reinserts them. Earlier years are left alone. |
| **Close-out** | SIS students | A student who drops out of the Aspire export is marked `is_active = FALSE`. The row isn't deleted. |

### Student identifiers

Different vendors identify students differently, so fact tables are keyed by whichever ID the source provides:

- `local_id`: the Aspire Student ID (`dim_students.local_id`)
- `ssid`: the Utah Statewide Student ID

`dim_students` holds both IDs, so any fact table can be joined back to demographics. ACT uses its own ID, which is translated to SSID through crosswalk files.

---

## Data sources

| Source key | What it is | How it's pulled | Extractor |
|---|---|---|---|
| `sis` | Student demographics (Aspire Demographic Export) | Logs into the Aspire web UI and posts to the export page | `sis_extractor.py` |
| `homeroom` | Current homeroom teacher assignments | SQL Server view `LEA.GetHomeRoom_View` | `homeroom_extractor.py` |
| `attendance` | Daily absences and tardies per student | SQL Server `dbo.AttendanceArchive`, totaled by student and day on the server | `attendance_extractor.py` |
| `enrollment` | Enrollment tracks, membership days, 160-day flag | SQL Server function `LEA.Enrollment_Membership_Detail2_ITVF` | `enrollment_extractor.py` |
| `wida` | WIDA ACCESS proficiency levels | SQL Server view `LEA.WingetAssessmentScores_View` *(custom; see below)* | `wida_extractor.py` |
| `acadience` | Acadience Reading and Math benchmarks (K–6) | Acadience Learning Online API | `acadience_extractor.py` |
| `acadience_pm` | Acadience progress monitoring (K–12) | Acadience Learning Online API | `acadience_pm_extractor.py` |
| `act` | ACT scores | CSV files in `data/act/` | `act_extractor.py` |
| `aspire_plus` | ACT Aspire Plus (pre-ACT) | CSV files in `data/aspire_plus/` | `aspire_plus_extractor.py` |
| `rise` | RISE state assessment (ELA, Math, Science, Writing) | CSV files in `data/rise/` | `rise_extractor.py` |
| `toscrf` | TOSCRF reading fluency screener | Google Sheets, through a service account | `toscrf_extractor.py` |
| `accountability` | USBE school accountability (student groups, TSI/ATSI/CSI, rank list) | Excel files in `data/accountability/` | `accountability_extractor.py` |

### Layout of the local file sources

`data/` is git-ignored. Download the state and vendor files and save them in this structure:

```
data/
├── act/
│   ├── act_<date>.csv              # ACT roster export; the newest file by name is used
│   └── crosswalk_<year>.csv        # columns ID_ACT, ID_StateAssign (ACT ID → SSID)
├── aspire_plus/
│   └── 24-25.csv                   # one file per year; the filename becomes school_year
├── rise/
│   └── 24-25/                      # one folder per year
│       ├── ela3.csv … ela8.csv
│       ├── math3.csv … math8.csv
│       ├── science4.csv … science8.csv
│       └── writing5.csv, writing8.csv
├── accountability/                 # USBE Excel files, named as listed in YEAR_SOURCES
│   └── 25StudentGroupAccountability.xlsx, 25CSI.xlsx, 25AllSchoolsRankList.xlsx, …
└── acadience/
    └── longitudinal_data/*.csv     # optional one-time backfill of past Acadience years
```

Run the pipeline from the repository root, because these paths are relative to the current directory.

---

## What ends up in the warehouse

**Dimensions (current state)**

| Table | Key | Notes |
|---|---|---|
| `dim_students` | `local_id` | Demographics, program flags (ELL, IEP, econ. disadvantaged, homeless, etc.), `is_active` |
| `dim_schools` | `school_id` | |
| `dim_homeroom` | `local_id` | Current homeroom course and teacher |

**Facts (history)**

| Table | Key |
|---|---|
| `fact_enrollment` | none (replaced by school year) |
| `fact_attendance_daily` | `local_id, date` |
| `fact_wida` | `local_id, school_year` |
| `fact_acadience_reading` / `fact_acadience_math` | `ssid, school_year, benchmark_period` |
| `fact_acadience_pm` | `ssid, school_year, assessment_date, measure` |
| `fact_rise_ela` / `_math` / `_science` / `_writing` | `ssid, school_year, grade` |
| `fact_aspire_plus` | `local_id, school_year` |
| `fact_act` | `act_id, test_date` |
| `fact_toscrf` | `local_id, school_year, assessment_window` |
| `fact_accountability_student_groups` | `school_year, school_id, student_group_code` |
| `fact_accountability_school_rank` | `school_year, school_id` |
| `fact_accountability_comparable_schools` | `school_year, school_id, student_group_code, peer_rank` |

Many assessment tables include `*_class_rank` and `*_quartile` columns. These are computed **within school, grade, year, and window** (quartile 4 = top 25%) by the shared helper `transform/_ranking.py`.

**Views for dashboards**

| View | Purpose |
|---|---|
| `v_acadience_reading` / `v_acadience_math` | Benchmark and progress-monitoring scores in one long table (one row per student, date, and measure) for the current year, built for line charts of individual students |
| `v_students_accountability` | Active students with IEP, ML, and 160-day enrollment flags |
| `v_accountability_dashboard` | Each school's student-group accountability scores, with district rank, USBE rank, and the points still needed to exit TSI/ATSI/CSI |

### Comparable schools

The accountability transformer finds the **5 most similar schools in the state** for each school and student group. A candidate must have the same school type and Title I status, and it must report a score for that same student group. Candidates are then ranked by closeness in enrollment and in that group's score. Matching on the student group, and not only the whole school, matters in Utah: some subgroups are concentrated in a few parts of the state, so a school that looks similar overall may not serve that subgroup at all. The full explanation is in `_compute_comparable_schools()` in `transform/accountability_transformer.py`.

---

## Setup

### Requirements

- Python 3.11+
- A PostgreSQL database the pipeline can create schemas in
- Network access to Aspire, the Aspire SQL Server, Acadience Learning Online, and the Google Sheets API (for whichever sources you use)

### Install

**With pip (most systems):**

```bash
git clone <this repo>
cd the-holysheet
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**With Nix:** the repo includes a `flake.nix`.

```bash
nix develop         # shell with Python, all dependencies, and the psql client
nix run             # runs run_etl.py (run it from the repo root)
```

### Configure

```bash
cp .env.example .env
```

Then fill in `.env`:

| Variable | Used for |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | The PostgreSQL warehouse |
| `ASPIRE_BASE_URL`, `ASPIRE_USERNAME`, `ASPIRE_PASSWORD` | Aspire web login for the demographic export |
| `ACADIENCE_EMAIL`, `ACADIENCE_PASSWORD`, `ACADIENCE_DISTRICT_ID` | Acadience Learning Online |
| `SQL_SERVER`, `SQL_DATABASE`, `SQL_USERNAME`, `SQL_PASSWORD` | Read-only login to the SQL Server behind Aspire (homeroom, attendance, enrollment, WIDA) |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | Path to a Google service-account JSON key (TOSCRF) |

> `config/settings.py` reads **every** variable when the pipeline starts, so all of them need a value even if you skip that source. If you don't use a source, set a placeholder and skip the source with `--skip` (see below).

Use an account with the fewest permissions that still works for each system. A read-only SQL Server login and an Aspire account that can only run the demographic export are enough.

---

## Running it

```bash
python run_etl.py                                   # all sources
python run_etl.py --skip toscrf,accountability      # leave some out
python run_etl.py --skip sis,homeroom,attendance,enrollment,wida   # e.g. during the Aspire year-end rollover
```

The source names for `--skip` are the keys in the [Data sources](#data-sources) table.

### Schedule it

Example cron entry that runs nightly at 2:00 AM and saves a log:

```cron
0 2 * * *  cd /opt/the-holysheet && .venv/bin/python run_etl.py >> logs/etl.log 2>&1
```

### Check on it

Every load writes a row to `staging.etl_runs`:

```sql
SELECT source, status, row_count, started_at, error_message
FROM staging.etl_runs
ORDER BY started_at DESC
LIMIT 20;
```

### One-time Acadience history backfill

The nightly run loads only the current Acadience year. To load earlier years, export them as CSVs into `data/acadience/longitudinal_data/` and run:

```python
from extract import acadience_extractor
from transform import acadience_transformer
from load import warehouse_loader as wl

raw = acadience_extractor.extract_historical()
wl.load_acadience(raw, acadience_transformer.transform(raw), skip_staging=True)
```

---

## Once-a-year maintenance

Do these at the start of each school year:

1. **`run_etl.py`**: update `CURRENT_SCHOOL_YEAR` (e.g. `2027` for 2026–27) and `ACADIENCE_YEAR_CODE`. Acadience year codes don't follow the calendar year. Look up the current code in ALO, which may not create it until enrollment opens.
2. **`extract/toscrf_extractor.py`**: add the new year to `YEARS` and create the Google Sheet named `"<yy-yy> TOSCRF"`, shared with the service account.
3. **`extract/accountability_extractor.py`**: when USBE publishes new accountability files, add an entry to `YEAR_SOURCES` with the new filenames and sheet names. USBE renames files and columns most years, so open the files and check the headers.
4. **New RISE, Aspire Plus, and ACT files**: save them under `data/` using the layout above.
5. **Aspire school track IDs**: if schools are added or reconfigured, update `SelectedTrackIDs` in `config/settings.py`.

---

## Adapting it for your district

The code is organized to make district-specific values easy to find. Here's everything tied to San Juan:

### Must change

| Where | What | Why |
|---|---|---|
| `.env` | All credentials, `ASPIRE_BASE_URL`, `ACADIENCE_DISTRICT_ID` | Your accounts and your Aspire instance |
| `config/settings.py` → `_ASPIRE_EXPORT_PAYLOAD` | `SelectedTrackIDs=…` | San Juan's school track IDs. To get yours, open the Demographic Export in Aspire with your browser's dev tools (Network tab), run an export, and copy the request body. |
| `extract/accountability_extractor.py` → `HOME_LEA_ID` | `880` | Your USBE LEA ID |
| `transform/accountability_transformer.py` → `HOME_LEA_ID` | `880` | Same as above. Change it in both places. |
| `extract/attendance_extractor.py` | `SJSD_CSS.dbo.AttendanceArchive` | The database name in your Aspire SQL Server is probably different |
| `transform/acadience_transformer.py` → `SCHOOL_NAME_MAP` | San Juan school names | Maps the inconsistent school names in Acadience exports to one standard name. Replace with your schools. |

### Probably change

| Where | What |
|---|---|
| `extract/wida_extractor.py` | `LEA.WingetAssessmentScores_View` is a **custom view** in our SQL Server, so it won't exist in yours. Write your own query for WIDA ACCESS scores that returns `StudentID, Year, Title, Score` in long format, or skip `wida`. |
| `extract/homeroom_extractor.py`, `enrollment_extractor.py` | `LEA.GetHomeRoom_View` and `LEA.Enrollment_Membership_Detail2_ITVF` live in the `LEA` schema. Ask your Aspire or IT staff whether yours have the same objects. |
| `extract/toscrf_extractor.py` | Only useful if you track TOSCRF in Google Sheets with `BOY`/`MOY`/`EOY` tabs. Otherwise skip it, or use it as a template for your own screener. |
| `transform/sis_transformer.py` | When a student has duplicate records, the one with the lowest `school_id` is kept, because San Juan numbers its elementary schools lowest. Check that this rule works with your school numbering. |
| `transform/enrollment_transformer.py` | `enrolled_160_days` uses Utah's 160-day full-year threshold |

### Probably fine as-is

- RISE, Aspire Plus, and ACT transformers. These use the standard Utah state and vendor export formats.
- Acadience extractors and transformers, apart from `SCHOOL_NAME_MAP`
- The accountability logic. It follows USBE's 225-point system (2021–22 onward) and filters by LEA ID.
- Everything in `load/` and `utils/`

### Don't use every source? Skip it

Add the source to `--skip` in your cron command, or remove its line from `SOURCES` in `run_etl.py`. Each source runs on its own, so leaving one out doesn't affect the others.

### Not on Aspire?

The SIS, homeroom, attendance, enrollment, and WIDA extractors are tied to Aspire. Whatever your SIS is, you can still use the rest of the pipeline. Write new extractors that return DataFrames with the **same raw column names** the transformers expect (each transformer's `RENAME`/`RAW_COLS` map lists them), or adjust those maps to your column names. Leave the transformers' output columns unchanged, so the warehouse tables and views keep working.

---

## Adding a new data source

1. **`extract/foo_extractor.py`**: write `extract()` so it returns the raw data unchanged.
2. **`transform/foo_transformer.py`**: write `transform(raw)` so it returns `{"foo": clean_df}`. For ranks and quartiles, use `transform/_ranking.add_rank_and_quartile()`.
3. **`load/warehouse_loader.py`**:
   - add a `CREATE TABLE IF NOT EXISTS warehouse.fact_foo (…)` statement in `_ensure_tables()` with a primary key
   - add `load_foo()` by copying an existing loader such as `load_wida()`. These loaders handle upsert, error handling, and `etl_runs` logging.
4. **`run_etl.py`**: add `run_foo()` and register it in `SOURCES`.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `KeyError: 'SQL_SERVER'` (or another variable) at startup | A variable is missing from `.env`. Every variable needs a value; see [Configure](#configure). |
| `AspireAuthError` | Wrong credentials, an expired password, or Aspire changed its login page |
| SIS loads 0 rows or the wrong schools | `SelectedTrackIDs` is out of date |
| `AcadienceExportError` with a 404 at the start of the year | `ACADIENCE_YEAR_CODE` is wrong, or ALO hasn't created the new year yet |
| `AccountabilityExtractError: file not found` | The filename in `YEAR_SOURCES` doesn't match the file in `data/accountability/` |
| A file source can't find its folder | The pipeline isn't running from the repo root |
| A source failed overnight | Look at `staging.etl_runs.error_message` and the cron log. The other sources still loaded. |

---

## License

MIT. See [LICENSE](LICENSE). Fork it, adapt it, and share improvements.
