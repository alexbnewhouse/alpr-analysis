# Land use variable: commercial versus residential

## What it is

There is no national parcel-level land use file. The standard substitute in
urban economics is the balance between **jobs located in** an area and **people
living in** it: many jobs and few residents means commercial, the reverse means
residential.

| Column | Definition |
|---|---|
| `jobs_total` | Jobs located in the unit (workplace) |
| `jobs_retail_food` | Of which retail trade + accommodation/food services |
| `resident_workers` | Employed people living in the unit |
| `pct_jobs_retail_food` | Retail share of local jobs |
| `jobs_per_resident_worker` | Jobs ÷ resident workers. >1 = net importer of commuters |
| `employment_ratio` | Jobs ÷ (jobs + resident workers). **0 = purely residential, 1 = purely employment** |

`employment_ratio` is the recommended headline term: bounded 0–1, symmetric,
and it does not explode in tracts with almost no residents the way
`jobs_per_resident_worker` does.

## Why it belongs in the model

Two distinct reasons.

**Siting.** Fixed ALPRs are typically mounted on arterial-adjacent commercial
strips, not in the middle of subdivisions. Commercial intensity is part of what
makes a location a candidate.

**The retail confound.** Roughly 14% of operator-tagged cameras in this data
belong to retail chains — Lowe's operates cameras across 543 distinct Census
places, Home Depot across 332. Those are corporate procurement decisions made
nationally and unrelated to local crime or policing. `pct_jobs_retail_food`
lets that channel be controlled or split out instead of pooled with police
deployments.

## Source

US Census Bureau, **Longitudinal Employer-Household Dynamics (LEHD), LODES
version 8**, published per state:

```
WAC (jobs by workplace block):  .../LODES8/<st>/wac/<st>_wac_S000_JT00_<year>.csv.gz
RAC (workers by residence):     .../LODES8/<st>/rac/<st>_rac_S000_JT00_<year>.csv.gz
Crosswalk (block → geography):  .../LODES8/<st>/<st>_xwalk.csv.gz
```

`S000` is all jobs; `JT00` is all job types. Industry columns follow NAICS
sectors; the two used here are **CNS07** (Retail Trade) and **CNS18**
(Accommodation and Food Services) — the consumer-facing, parking-lot-bearing
sectors.

## Method

Blocks are the unit of publication. LODES ships a crosswalk mapping every 2020
block (`tabblk2020`) to `trct`, `cty`, `stplc` and `zcta`, so **all four
analysis levels are reached by aggregation with no spatial join** — none of the
boundary-sharing problems that affect the road measure apply here. Units
straddling a state line are summed across both states' files.

## Vintage and coverage

The target vintage is **2022**, with fallback to 2021 then 2020 per state, so a
state whose latest release is older is included rather than dropped. The year
actually used is reported at build time.

| | |
|---|---|
| States on 2022 | 49 + DC |
| **Michigan** | **2021** — no 2022 release exists |
| **Alaska** | **excluded — no LODES in any year**; Alaska does not participate in LEHD |
| National jobs | 146,859,721 |

Alaska's exclusion is immaterial for this study: it has zero mapped ALPRs. But
any specification using these variables should exclude Alaska explicitly rather
than let it drop silently.

Coverage against the tract model frame:

| | |
|---|---|
| Tracts with land use | 83,920 of 84,415 (99.4%) |
| **Camera-bearing tracts with land use** | **100.0%** |
| Cameras in tracts lacking land use | 27 of 124,407 |

## Discriminating power

Median values, zero-camera versus camera-bearing tracts:

| Variable | Zero | Camera | Ratio |
|---|---|---|---|
| `road_density_km_sqkm` | 0.449 | 0.796 | 1.77 |
| `road_km_arterial` | 4.32 | 6.64 | 1.54 |
| `employment_ratio` | 0.298 | 0.385 | 1.29 |
| `pct_jobs_retail_food` | 0.163 | 0.198 | 1.22 |
| *median household income* | *74,863* | *75,865* | *1.01* |
| *poverty rate* | *0.136* | *0.135* | *0.99* |

The exposure and land-use variables separate the two groups an order of
magnitude better than the socioeconomic variables do. This is itself a
substantive result: where cameras go is primarily a question of road and
commercial geography, and only secondarily one of neighbourhood demographics.

## Caveats

- **UI-reported employment only.** LODES covers jobs reported through state
  unemployment insurance systems, so it largely omits self-employment and its
  federal-employment coverage is partial. National total 146.9M against BLS
  establishment employment of roughly 157M.
- **Noise-infused** for confidentiality. Immaterial once blocks are aggregated
  to tracts; it would matter at block level.
- **Workplace, not land.** A high-rise office tower and a sprawling retail park
  with the same job count score alike, though they occupy very different
  footprints.
- **Vintage mismatch.** 2022 (2021 for Michigan) is not matched to the camera
  observation dates.

## Files

```
data/interim/landuse_tract.parquet
data/interim/landuse_place.parquet
data/interim/landuse_county.parquet
data/interim/landuse_zcta.parquet
```

## Code

`flock_alpr/landuse.py`

```python
from flock_alpr import landuse
landuse.build("tract")     # or "place", "county", "zcta"
```
