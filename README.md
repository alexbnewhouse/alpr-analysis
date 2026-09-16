# flock-analysis

Working folder for **"What the Flock? A multilevel analysis of ALPR adoption, intensity, and rejection"** (with Stone Neilon). APRL presentation **Fri Nov 6, 2026**.

- Draft (read-only for now): `~/Dropbox/Apps/Overleaf/Memo: Flock Camera Adoption/main.tex`
- Notion hub: "Flock ALPR Paper → Nov 6" (private, created 2026-09-13)
- Stone's code and data: `alpr_handoff/` and `alpr_ban_dataset/` (snapshots handed off 2026-09-16; see below)
- This repo: https://github.com/alexbnewhouse/alpr-analysis

## Layout

```
alpr_pipeline/    Python: OSM/DeFlock camera harvest → SQLite → census geography → tract panel
                  (first-round work, Aug 2026; see its README and DATA_MANIFEST.md)
alpr_pipeline/data  1 GB of harvests, exports, caches, panels — gitignored; symlink to ~/flock_research/alpr_pipeline/data
alpr_handoff/     Stone's pipeline (`flock_alpr/`), analysis scripts + model frames (`external/`), LaTeX + method notes (`docs/`), 79 tests
alpr_ban_dataset/ Stone's ALPR pause/ban register (151 places, 28 counties) + the Nexis/DeFlock sources and parser scripts
notes/            audit of the draft, data-sourcing guide, MLM crash course, Mundlak review, references
scripts/          numbered drivers (R for covariate builds, Python for pipeline utilities); R functions in scripts/R/
tests/testthat/   R unit tests on fixed-width fixtures (Rscript -e 'testthat::test_dir("tests/testthat")')
data/raw/         downloads (gitignored; each script re-fetches what it needs)
data/out/         the CSVs handed to Stone + a coverage report per build (committed)
.venv/            Python env for alpr_pipeline (gitignored): python3 -m venv .venv && .venv/bin/pip install -r alpr_pipeline/requirements.txt
```

Two upstream checkouts used as evidence for the data chain — the DeFlock site (`deflock/`) and the
maps.deflock.org app (`deflockhopper_maps/`) — stay in `~/flock_research/` and are **not** vendored here;
the pipeline README cites file paths in them.

## Builds

| Script | Source | Outputs | Status |
|---|---|---|---|
| `alpr_pipeline` (`fetch`, `covariates`) | OSM via DeFlock derived feed + full Overpass harvest; ACS 2023; VEST 2020; AIP; Kaplan UCR 2023 | `alpr_cameras_us.parquet` (124,623 cameras), `alpr_us_full.sqlite` (Overpass, 20k editors), `tract_panel.parquet` (85,381 tracts, 62 cols) | ✅ 2026-08-04 snapshot; tests pass on macOS 2026-09-13 |
| `scripts/01_cog2022_police.R` | 2022 Census of Governments, Finance individual-unit file | `place_police_2022.csv`, `cousub_police_2022.csv`, `county_sheriff_2022.csv`, `cog2022_coverage.md` | ✅ 2026-09-13 |
| `scripts/02_pipeline_manifest.py` | the pipeline's data directory | `alpr_pipeline/DATA_MANIFEST.md` | ✅ 2026-09-13 |

Run from the project root: `Rscript scripts/01_cog2022_police.R` (≈1 s after the 10 MB download). Needs R with readr, dplyr, tidyr, stringr; testthat for the tests.

## My deliverables (CSVs keyed on GEOID)

| File | Contents | Feeds |
|---|---|---|
| `place_police_2022.csv` ✅ | CoG 2022 municipal police ops (E62) + construction (F62), flags, per capita; 19,401 city-type governments keyed on place GEOID | place models |
| `cousub_police_2022.csv` ✅ | same for 15,981 township-type governments keyed on county-subdivision GEOID (strong-MCD states) | place/tract models via spatial join |
| `county_sheriff_2022.csv` ✅ | county E62/F62, municipal police total in county, `county_share_police`; 3,029 county governments | county models; county covariates in tract/place models |
| `county_sheriff.csv` (v2) | + sworn 2018 (CSLLEA), patrol function, elected, 287(g), LEMAS ALPR flag | county models |
| `place_crime.csv` | Kaplan Return A via LEAIC: violent / property / MVT rates, months, coverage | place models |
| `county_crime.csv` | same at county + coverage share + CDC homicide | county models; cross-level covariate |
| `agency_flock.csv` | transparency-portal camera counts & sharing (optional) | validation / public-private split |

See `notes/data-sourcing-guide.md` for sources and `notes/multilevel-crash-course.md` for how these enter the models.

## Stone's handoff (received 2026-09-16)

Two folders, copied in unmodified so Stone's docs and relative paths still work. Read
`alpr_handoff/HANDOFF.md` and `alpr_handoff/CLAUDE.md` first, then `alpr_ban_dataset/HANDOFF_ban_dataset.md`.

**`alpr_handoff/`** — the adoption/intensity side.
- `external/data/model_frame_{tract,place,county,zcta}.parquet` — the analysis frames, full universe incl. zero-camera units. Keys: `tract_geoid` (11), `place_geoid` (7), `county_fips` (5), `zcta` (5), all **character**.
- `external/data/camera_dataset.parquet` (124,416 cameras × 284 cols) and `cameras_geocoded.parquet`.
- `data/interim/` — ACS 2023, TIGER arterial roads, LODES land use, FBI crime by ORI, FBI agency roster.
- `external/hurdle_fe.R` — the recommended Mundlak/CRE hurdle (glmmTMB); `table_*_ladder.R` — the spec tables; `docs/*.tex` — model section + equations.
- Run from inside `alpr_handoff/`: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest -m "not network"`; `Rscript external/hurdle_fe.R`.
- Not included (rebuildable, gitignored): HTTP cache, TIGER shapefiles, fitted `.rds`, the source `alpr_cameras_us.xlsx`.

**`alpr_ban_dataset/`** — the rejection side.
- `register/alpr_decisions_merged.csv` is **the file to edit** (151 places; `verified` is FALSE on every row). `register/alpr_decisions_counties.csv` holds 28 county decisions with no place GEOID.
- `sources/nexis/*.DOCX` are Nexis Uni full-text exports and are **gitignored** (licensed content; this repo is public). They stay on local disks only; `sources/nexis/nexis_candidates.csv` (headlines, dates, snippets) is committed.
- The scripts import `flock_alpr` from `alpr_handoff/` and expect Stone's full repo layout; they are here for reference.
