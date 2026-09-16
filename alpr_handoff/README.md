# Flock ALPR Adoption Research Pipeline

Assembles US automated license plate reader (ALPR) camera locations and agency
adoption records into analysis-ready panels, for studying what predicts Flock
Safety camera adoption.

## Why not deflock.org

deflock.org is a JavaScript client, not a data source. Every path on the site
returns the same ~3KB HTML shell; the map is rendered from OpenStreetMap nodes
tagged `surveillance:type=ALPR`. This pipeline queries OSM directly, which is
what the site itself does — cleaner, complete, and with version history.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest
```

Stages 1–4 need no credentials. Stage 5 needs two free API keys:

```bash
export CENSUS_API_KEY=...   # https://api.census.gov/data/key_signup.html
export FBI_API_KEY=...      # https://api.data.gov/signup/
```

## Running

```bash
.venv/bin/python -m flock_alpr aos                    # Atlas of Surveillance
.venv/bin/python -m flock_alpr osm                    # all states (slow)
.venv/bin/python -m flock_alpr osm --states NC SC     # a subset
.venv/bin/python -m flock_alpr geocode                # spatial join
.venv/bin/python -m flock_alpr history --states NC    # ohsome discovery series
.venv/bin/python -m flock_alpr covariates             # ACS + FBI crime
.venv/bin/python -m flock_alpr panel                  # assemble panels
```

Every network response is cached under `data/raw/cache/` keyed by request hash,
so re-running is free and a parser bug never costs another API round trip. Pass
`--force` to bypass the cache.

## Stages

| Stage | Module | Output |
|---|---|---|
| 1 | `extract_osm` | `raw/osm_alpr_nodes.parquet` — one row per camera |
| 2 | `extract_osm_history` | `raw/osm_alpr_history.parquet` — county × quarter |
| 3 | `extract_aos` | `raw/aos_alpr_agencies.parquet` — one row per agency-vendor |
| 4 | `geocode` | `interim/cameras_geocoded.parquet` — cameras + ZCTA/place/county |
| 5 | `covariates` | `interim/acs_*.parquet`, `interim/crime_by_ori.parquet` |
| 6 | `build_panel` | `panel_geo_{zcta,place,county}.parquet`, `panel_agency.parquet` |

## Current national extract

125,192 ALPR nodes across 50 states (Alaska has none), of which 103,529 are
Flock. Spatial join assigns 100% to a county, 99.9% to a ZCTA, and 80.7% to a
Census place — the place gap is real, not a defect: many cameras sit in
unincorporated areas outside any incorporated place.

Panels: 13,477 ZCTAs, 8,270 places, 2,279 counties, 4,015 agencies.

## Data-quality notes

Two bugs were found by comparing this pipeline against deflock.org's own
extraction scripts ([FoggedLens/deflock](https://github.com/FoggedLens/deflock),
`serverless/alpr_*/src/*.py`). Both are fixed; both are worth knowing about if
you extend the code.

**Vendor lives in more than one tag.** Reading `manufacturer` alone missed 744
California nodes tagged `brand=Flock Safety`. The undercount ranged from 0.01%
(Florida) to 36% (Virginia) — non-random across geographies, so it would have
biased exactly the spatial correlates under study. `extract_osm.coalesce_vendor`
now falls back through `manufacturer` → `brand` → `surveillance:manufacturer` →
`surveillance:brand` into a single `vendor` column. **Use `vendor`, never
`manufacturer`, to identify Flock.**

**Overpass mirrors lag the primary.** During a run where Pennsylvania fell
through to `overpass.kumi.systems`, that mirror returned 1,526 nodes against
the primary's 2,347 — a 35% shortfall, silently. A failed request is visible; a
short response is not. Each state's `source_endpoint` is now recorded, and a
checkpoint filled from a mirror is retried against the primary on the next run.
The run warns if any state's data came from a mirror.

**Not yet normalised:** `operator_type` arrives with inconsistent casing and
granularity (`Public`/`public`, `municipal police`/`police department`). Clean
it before using it as a factor.

## Data sources

- **OpenStreetMap** via [Overpass](https://overpass-api.de) — camera locations
  and tags (`manufacturer`, `operator`, `operator:type`, `direction`).
- **[ohsome API](https://api.ohsome.org)** (HeiGIT) — OSM history, for the
  quarterly discovery series and its mapping-effort denominators.
- **[EFF Atlas of Surveillance](https://atlasofsurveillance.org)** — agency-level
  adoption records. Critically, the `NEWAOSNUMBER (ORI9)` column yields a valid
  FBI ORI on ~98% of Flock rows, giving an exact join to UCR/NIBRS crime data.
- **Census ACS 5-year** — income, poverty, race, education, tenure.
- **FBI Crime Data Explorer** — agency-level offense counts by year.

## The timing caveat — read this before using the panel

**Both time signals measure observation, not deployment.**

OSM timestamps record when a volunteer *mapped* a camera. DeFlock launched
around October 2024, so mapping is heavily front-loaded and driven by activist
attention. In the Atlas of Surveillance, of the Flock records carrying an
explicit "as of" date, the overwhelming majority say 2025 — that is EFF's
collection sweep, not a wave of adoptions.

The danger is specific: volunteer mapping intensity and media coverage are both
plausibly correlated with income, education, and local politics — the exact
covariates under test. Used naively, the panel would manufacture the very
correlations the study is trying to detect.

Two instruments are built in so this is measurable rather than merely
disclaimed:

**Mapping-effort denominators.** Stage 2 pulls `total_nodes` (all OSM nodes) and
`contributors` over the identical polygons and quarters as `discovery_count`.
Normalising by these answers whether ALPR mapping moved independently of
general OSM activity. In the North Carolina validation run it clearly did:
total OSM nodes grew ~2% (5.04M → 5.15M) while ALPR discovery went 2 → 1,984.

**Discovery-lag calibration.** Stage 6 compares two independent observation
dates per agency — OSM first-seen and Atlas first-citation. The distribution of
the gap estimates discovery lag. A stable distribution is partially correctable;
one that varies with income or urbanicity is itself a finding.

Enforced conventions:

- OSM-derived counts are always named `discovery_count`, never
  `installed_count`. A test in `tests/test_extract_osm_history.py` fails the
  build if that name appears as a column anywhere in `flock_alpr/`.
- The trailing quarter of any ohsome run is partial (its interval runs past the
  end of the history database). It carries `quarter_complete=False`. Flow
  measures like `contributors` are null there — null, not zero. Filter on
  `quarter_complete` before computing rates.

Recommended posture: treat the cross-section as the primary analysis and the
panel as descriptive, published with the diagnostics attached.

## Unit of analysis

Two units, because the two halves of the research question have different
natural geographies.

**Geographic** (ZCTA, Census place, county). Cameras are points; geography comes
from one spatial join that assigns all three levels. Note that USPS ZIP codes
are delivery routes, not areas — this uses Census ZCTAs, which approximate
them. Cameras often sit on roads forming ZCTA boundaries, so a small share of
assignments are arbitrary at the margin. State that in methods.

**Agency** (ORI). Flock contracts are signed by police departments, sheriffs'
offices, and municipalities — not by ZIP codes — and crime is reported by
agency. The ORI-keyed panel is where the crime question is properly answerable.

## Licensing

OpenStreetMap data is ODbL: attribution required, with share-alike obligations
for derived databases — relevant if you publish the assembled panel. Atlas of
Surveillance is CC-BY. Cite both in methods.

## Layout

```
flock_alpr/          pipeline modules, one per stage
tests/               network-free tests against committed fixtures
docs/superpowers/    design spec and implementation plan
data/                all outputs (gitignored)
```
