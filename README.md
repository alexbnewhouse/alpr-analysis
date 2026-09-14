# flock-analysis

Working folder for **"What the Flock? A multilevel analysis of ALPR adoption, intensity, and rejection"** (with Stone Neilon). APRL presentation **Fri Nov 6, 2026**.

- Draft (read-only for now): `~/Dropbox/Apps/Overleaf/Memo: Flock Camera Adoption/main.tex`
- Notion hub: "Flock ALPR Paper → Nov 6" (private, created 2026-09-13)
- Stone's modeling repo: *ask* (the draft references `docs/vif_diagnostics.txt`)
- This repo: https://github.com/alexbnewhouse/aplr-analysis

## Layout

```
alpr_pipeline/    Python: OSM/DeFlock camera harvest → SQLite → census geography → tract panel
                  (first-round work, Aug 2026; see its README and DATA_MANIFEST.md)
alpr_pipeline/data  1 GB of harvests, exports, caches, panels — gitignored; symlink to ~/flock_research/alpr_pipeline/data
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
