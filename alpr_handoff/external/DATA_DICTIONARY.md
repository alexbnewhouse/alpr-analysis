# Data dictionary

Every file here is Parquet. Read GEOID columns as **character** — several are
zero-padded and coercing them to numeric silently mis-joins every state with a
FIPS code below 10 (CA, AL, AK, AR, CO, CT, DE, DC, FL, GA).

```r
library(arrow)
d <- read_parquet("external/data/model_frame_tract.parquet")
```

```python
import pandas as pd
d = pd.read_parquet("external/data/model_frame_tract.parquet")
```

---

## `camera_dataset.parquet` — one row per camera (primary analytical file)

124,416 cameras x 240 columns. Every camera carries its own attributes, its
four geography keys, and the **full covariate set for each geography that
contains it**, suffixed by level.

```r
cameras <- arrow::read_parquet("external/data/camera_dataset.parquet")
tract_vars <- grep("_tract$", names(cameras), value = TRUE)
```

### Camera attributes (26 columns, unsuffixed)

`osm_id`, `lat`, `lon`, `state`, `osm_type`, `country_code`, `brand_raw`,
`operator_raw`, `vendor`, `is_flock`, `direction_raw`, `direction_deg`,
`direction_count`, `directions_all`, `surveillance_zone`, `mount_type`, `ref`,
`start_date`, `osm_version`, `osm_timestamp`, `first_seen_snapshot`,
`last_seen_snapshot`, plus the four geography keys.

### Contextual covariates (suffixed by scale)

| Suffix | Columns | Coverage (median income) |
|---|---|---|
| `_tract` | 51 | 98.8% |
| `_place` | 56 | 80.4% |
| `_county` | 56 | 100.0% |
| `_zcta` | 51 | 99.2% |

Every ACS variable listed under the analysis frames appears once per level, so
`median_hh_income_tract`, `median_hh_income_place`, `median_hh_income_county`
and `median_hh_income_zcta` all exist. Place columns are null for the ~19% of
cameras outside any incorporated place.

Also per level: `n_cameras_<level>` and `n_flock_<level>` — how many cameras
share that unit, i.e. local density around this camera.

### Crime columns

`violent_crime_county` (92.0%), `property_crime_county`, `n_agencies_county`,
`violent_crime_place` (43.6%), `property_crime_place`, `n_agencies_place`,
plus `violent_rate_county` / `property_rate_county` and the place equivalents,
per 100,000 using that geography's population.

### The scales are not redundant

Tract and county median income correlate only **0.54**, with a mean absolute
gap of **$26,230**. A camera in a wealthy tract of a poor county is a
different observation from one in a poor tract of a wealthy county, and this
file lets you separate them.

### What this file cannot do

There are **no rows for places without cameras**. It answers "what kind of
place is a camera in", not "what predicts a place having cameras". The second
question needs the zero universe — use `model_frame_<level>.parquet`.

---

## `model_frame_<level>.parquet` — the analysis frames

One row per geographic unit, covering the **complete universe** of units, not
only those with cameras. Levels: `tract`, `place`, `county`, `zcta`.

| Level | Units | With ≥1 camera | Key column | Width |
|---|---|---|---|---|
| tract | 84,415 | 38,840 (46.0%) | `tract_geoid` | 11 |
| place | 32,041 | 8,242 (25.7%) | `place_geoid` | 7 |
| county | 3,235 | 2,272 (70.2%) | `county_fips` | 5 |
| zcta | 33,791 | 13,450 (39.8%) | `zcta` | 5 |

### Outcome and density columns

| Column | Type | Meaning |
|---|---|---|
| `n_cameras` | int | ALPR cameras mapped in this unit. **Zero-filled**, never null. |
| `cameras_per_10k` | float | `n_cameras` per 10,000 residents |
| `flock_per_10k` | float | Same for Flock only |
| `cameras_per_sqkm` | float | `n_cameras` per km² of land |
| `pop_density_sqkm` | float | Residents per km² of land |
| `land_area_sqkm` | float | Land area from TIGER (excludes water) |
| `n_flock` | int | Subset with a Flock vendor tag |
| `n_retail` | int | Subset whose operator matches a retail chain |
| `n_police` | int | Subset whose operator matches a law-enforcement pattern |
| `has_camera` | bool | `n_cameras > 0` |

`n_retail` and `n_police` are derived from `operator_raw`, which is **82.3%
null**. They are lower bounds, not a partition: a camera absent from both is
usually unlabelled rather than neither.

### Geography keys

| Column | Present at | Notes |
|---|---|---|
| `tract_geoid` | tract | 11 chars = state(2) + county(3) + tract(6) |
| `county_fips` | tract, place, county, zcta | 5 chars. On tract frames = `tract_geoid[:5]`; on place and ZCTA frames assigned by centroid |
| `place_geoid` | tract, place | 7 chars = state(2) + place(5). On tract frames, the place containing the tract centroid (65% of tracts fall in one) |
| `state_fips` | place | 2 chars |
| `zcta` | zcta | 5 chars |

Only `tract_geoid → county_fips` is an exact containment. Place and ZCTA
assignments to county, and tract assignment to place, are **centroid-based**:
a unit straddling a boundary is credited to one side.

Tract nests inside county; ZCTA nests inside nothing. That is the reason
county fixed effects are available at tract level but not at ZCTA level.

### Covariates — ACS 2023 5-year, all levels

Raw counts are retained alongside derived shares so you can re-derive or
re-base anything.

| Column | Meaning |
|---|---|
| `population` | Total population (B01003) |
| `median_age` | B01002 |
| `median_hh_income` | Median household income (B19013) |
| `per_capita_income` | B19301 |
| `gini_index` | Income inequality (B19083) |
| `median_home_value` | B25077 |
| `median_gross_rent` | B25064 |
| `pct_white`, `pct_black`, `pct_amerindian`, `pct_asian`, `pct_two_or_more`, `pct_hispanic` | Shares of B02001 / B03003 |
| `pct_foreign_born` | Share of B05002 |
| `pct_below_poverty` | Share of the poverty universe (B17001), **not** total population |
| `pct_bachelors_plus` | Bachelor's + master's + professional + doctorate, over adults 25+ (B15003) |
| `pct_unemployed` | Share of the civilian labour force (B23025) |
| `pct_owner_occupied`, `pct_renter_occupied` | Shares of occupied units (B25003) |
| `pct_no_vehicle` | Owner + renter no-vehicle households, over B25044 |
| `pct_drove_alone`, `pct_public_transit` | Shares of workers (B08301) |
| `acs_year` | 2023 |

**Each share uses its own ACS universe.** Education is over adults 25+,
poverty over the poverty universe, commute over workers. Dividing everything
by total population — a common shortcut — understates every rate, by a
different factor in each unit.

Census jam values (−666666666 and similar) are converted to null, not left as
huge negatives.

### Crime — FBI UCR/NIBRS

Crime is a **jurisdiction-level** quantity: police report for the area they
police, not for a Census polygon. It is therefore aggregated to the two
jurisdictions that exist in the data and broadcast down to finer units. A tract
inherits the crime of the county and the municipality that contain it.

| Column | Meaning | Present at |
|---|---|---|
| `violent_crime_county` | Mean annual violent offences 2019–2023, all agencies in the county | all levels |
| `property_crime_county` | Same, property offences | all levels |
| `n_agencies_county` | Agencies contributing | all levels |
| `violent_crime_place` | Same, city agencies inside that municipality | tract, place |
| `property_crime_place` | Same, property offences | tract, place |
| `n_agencies_place` | City agencies contributing | tract, place |

Coverage:

| Level | `*_county` | `*_place` |
|---|---|---|
| tract | 89.3% | 34.1% |
| place | 89.6% | 13.2% |
| county | 86.4% | — |
| zcta | 89.0% | — |

Place coverage is low because most municipalities have no police department of
their own — they are policed by the county sheriff, so the county columns are
the right measure there, not a missing value to be imputed.

**This does not vary within a jurisdiction.** Every tract in a county shares
that county's crime figure. Do not read within-county variation into it, and
note that county fixed effects will absorb `*_county` entirely, making it
inestimable in such a model.

**Missingness is clustered by state**, not random — it reflects known UCR/NIBRS
participation gaps. Agencies with no data at all, by state: Connecticut 65%,
Colorado 57%, Kentucky 39%, New York 38%, North Carolina 32%. Any analysis
using crime should report this or absorb it with state effects.

Only `City` and `County` agency types are included; state police, university,
and tribal agencies are excluded to avoid double-counting offences already
reported within a municipality.

Null crime means no agency matched — treat as missing, never as zero crime.

---

## `cameras_geocoded.parquet` — camera level

One row per camera (124,416 after excluding territories), with the geography
keys appended. Use this to re-aggregate at a different level or with different
filters.

Assignment rates: tract 100.0%, county 100.0%, ZCTA 99.9%, place 80.7%. The
place gap is real — roughly 19% of cameras sit in unincorporated areas outside
any incorporated place.

---

## Interim files (`data/interim/`)

| File | Rows | Contents |
|---|---|---|
| `acs_tract.parquet` | 84,400 | ACS by tract |
| `acs_place.parquet` | 32,325 | ACS by place |
| `acs_county.parquet` | 3,222 | ACS by county |
| `acs_zcta.parquet` | 33,772 | ACS by ZCTA |
| `fbi_agencies.parquet` | 19,616 | ORI, agency name, type, county, station lat/lon |
| `crime_by_ori.parquet` | 92,904 | Agency-year offence and clearance counts |
| `crime_fetch_failures.parquet` | — | Which requests failed and why (written on future runs) |

### `crime_by_ori.parquet` columns

| Column | Meaning |
|---|---|
| `ori9` | FBI Originating Agency Identifier |
| `year` | Calendar year |
| `actual_violent_crime`, `actual_property_crime` | Offences |
| `cleared_violent_crime`, `cleared_property_crime` | Clearances |
| `months_reported` | **How many of 12 months the agency actually reported** |

`months_reported` matters. The API returns monthly buckets and many agencies
report only part of the year; summing those naively makes a low-*reporting*
agency look like a low-*crime* agency. The panel builder keeps only
agency-years with all 12 months. Apply the same filter for any other use.

---

## Known limitations

**The outcome measures mapping, not installation.** `n_cameras` counts cameras
that OpenStreetMap volunteers have recorded. Mapping effort plausibly rises
with income and education, so income coefficients are partly a discovery
artifact. There is no correction applied in these files.

**Operator labels are sparse.** 82.3% of cameras have no operator tag, so
police/retail splits rest on a non-random 18%. Tracts with more educated
populations are significantly more likely to have tagged operators.

**Crime coverage is incomplete and state-clustered.** 1,539 of 14,811 agencies
(10.4%) returned no data, concentrated in specific states (CT 65%, CO 57%, KY
39%, NY 38%, NC 32%). The 12-month filter removes more: 69,421 of 92,904
agency-years survive it (74.7%). Check `n_agencies_county` before treating
crime coverage as representative.

**Territories excluded.** Puerto Rico and the Virgin Islands appear in the
camera source but not in TIGER state files or most ACS products, so they are
dropped from the panels (207 camera rows).

**Rate columns are unstable in tiny units.** `cameras_per_10k` reaches 385 in
a county of 52 people with 2 cameras. Prefer a count model with
`offset(log(population))` over modelling the rate directly, or filter on a
minimum population.

**Snapshot, not panel.** These are cross-sections. `osm_timestamp` records
when a camera was first mapped, which is not when it was installed.
