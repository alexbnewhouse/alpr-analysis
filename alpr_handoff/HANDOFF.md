# ALPR Adoption Study — Handoff

**Working with an AI agent?** `CLAUDE.md` in this directory is the operational
contract — invariants, tooling constraints, and bugs already fixed. Point your
agent at it.

Everything built so far: the data pipeline, the assembled datasets, the models,
and the decisions behind them. Written so you can re-run the analysis at any
geographic level without reconstructing the reasoning.

---

## 1. What the project is

**Question.** What predicts the placement of automatic license plate readers
(ALPRs) across the United States? Specifically, is income associated with
adoption, and is crime?

**Unit of analysis.** Primary results are at Census tract. The same data is
built at place, county and ZCTA so results can be shown at multiple scales.

**Outcome.** Count of ALPR cameras per geographic unit. 124,416 cameras
nationally, 103,739 of them Flock Safety.

---

## 2. The single most important caveat

**The outcome measures cameras that volunteers have MAPPED, not cameras that
exist.** The source is OpenStreetMap, populated largely through the DeFlock
project. Mapping effort plausibly rises with income and education, which are
also covariates of interest. Treat coefficients on income and education as
partly a discovery artefact.

**Second caveat: the outcome pools public and private cameras.** 82.3% of
cameras have no operator recorded. Among the 17.7% that do: 60.9% law
enforcement, 13.7% retail, 0.5% HOA, 25.0% unclassifiable. Retail chains
(Lowe's operates cameras across 543 Census places, Home Depot 332) make siting
decisions nationally, unrelated to local policing. We cannot put a defensible
number on the private share. Describe the outcome as *ALPR presence*, not
police surveillance.

---

## 3. Data sources

| Source | What it provides | Access |
|---|---|---|
| **OpenStreetMap** (Overpass) | Camera locations and tags | Public, no key |
| **EFF Atlas of Surveillance** | Agency-level Flock adoption, ORI codes | Public CSV |
| **Census ACS 5-year 2023** | Socioeconomic covariates | Free API key |
| **TIGER/Line 2024** | Boundaries, land area, roads | Public |
| **FBI Crime Data Explorer** | Agency-level crime counts | Free api.data.gov key |
| **LEHD LODES 8** | Jobs by workplace/residence | Public |
| **ohsome API** | OSM history (not yet run nationally) | Public |

**deflock.org is not a data source.** It is a JavaScript client that renders
OSM nodes tagged `surveillance:type=ALPR`. Query OSM directly.

---

## 4. Datasets produced

All Parquet. **Read GEOID columns as character** — several are zero-padded and
coercing to numeric silently mis-joins every state with FIPS below 10 (CA, AL,
AK, AR, CO, CT, DE, DC, FL, GA).

### `external/data/model_frame_<level>.parquet` — the analysis frames

One row per geographic unit, covering the **complete universe** including units
with zero cameras. This matters: analysing only camera-bearing units conditions
on the outcome and overstates the mean count by 2.2x.

| Level | Units | With cameras | Key column |
|---|---|---|---|
| tract | 84,415 | 38,840 (46.0%) | `tract_geoid` (11 char) |
| place | 32,041 | 8,242 (25.7%) | `place_geoid` (7 char) |
| county | 3,235 | 2,272 (70.2%) | `county_fips` (5 char) |
| zcta | 33,791 | 13,450 (39.8%) | `zcta` (5 char) |

### `external/data/camera_dataset.parquet` — camera level

124,416 cameras x 284 columns. Each camera carries its own attributes plus the
full covariate set for the tract, place, county and ZCTA containing it,
suffixed by level (`median_hh_income_tract`, `median_hh_income_county`, ...).
Use for "what kind of place is a camera in"; it has no rows for camera-less
areas so it cannot answer "what predicts having any cameras".

### `data/interim/` — inputs for rebuilds

ACS, roads, land use and crime by level; FBI agency roster; geocoded cameras.

---

## 5. Variables

Full documentation: `docs/table_variable_list.tex`, `docs/DATA_DICTIONARY.md`
(in `external/`), `docs/road_exposure.md`, `docs/landuse.md`.

The tract model uses 14 terms in four blocks:

**Exposure and scale** — `log_pop`, `log_area`, `ld_c_sq` (centred log density
squared), `log_road_km`, `has_arterial`

**Land use** — `employment_ratio`, `pct_jobs_retail_food`

**Economic** — `log_income`, `pct_below_poverty`

**Composition** — `pct_black`, `pct_hispanic`, `pct_asian` (White omitted)

**Other** — `pct_renter_occupied`, `median_age`

### Constraints that must be preserved

- **`log_pop`, `log_area`, `log_density` cannot all enter.** `log_density` is
  exactly `log_pop - log_area`. At tract level use `{log_pop, log_area}`: VIFs
  1.3 and 4.9. The alternative `{log_area, log_density}` gives 18.5 and 26.6,
  because tracts are built to hold ~4,000 people so density is nearly
  `-log_area` (r = -0.972). **This will differ at other levels** — re-check.
- **Centre log density before squaring.** Uncentred VIF 22, centred 1.8.
- **`pct_white` is the omitted reference.** Race shares are compositional.
- **Never enter owner and renter share jointly** — exact complements.
- **Excluded as collinear with income** (all r > 0.69): per-capita income, home
  value, gross rent, education.
- **Excluded as bad controls** (consequences of urban form that steal density's
  coefficient): `pct_no_vehicle`, `pct_drove_alone`, `pct_public_transit`.

---

## 6. Modelling strategy

### Why a hurdle

54.0% of tracts have no camera. Variance-to-mean is 5.37 unconditionally and
**still 3.64 among positive counts**, so overdispersion is not merely the zero
mass. Poisson implies 22.9% zeros against 54.0% observed.

Hurdle rather than zero-inflated because the two decisions are sequential —
whether to place any reader, then how many — not a mixture of two zero types.
The two fit almost identically (2 AIC points apart on 82,916 observations), so
the choice rests on the substantive argument.

Evidence it matters: **poverty enters the two margins with opposite signs**
(negative on adoption, positive on intensity). A single count model averages
them to approximately zero.

### The two margins

**Adoption** — logit on `1(y > 0)`. This *is* a standalone logit; the hurdle's
zero component and `glm(I(y>0) ~ x, family=binomial)` are identical to 9.5e-10.

**Intensity** — zero-truncated negative binomial on `y > 0`.

### Why county effects are handled the way they are

Fixed effects would be standard, but **the intensity margin needs a
zero-truncated NB and no estimator combines that with thousands of fixed
effects**:

| | Truncated NB | Many fixed effects |
|---|---|---|
| `pscl` | yes | no |
| `fixest` | no | yes |
| `glmmTMB` | yes | random effects only |

We therefore use **Mundlak correlated random effects**: a county random
intercept plus the county mean of every covariate. Adding the county means
means a covariate's own coefficient can only reflect deviation from its county
average, which is the fixed-effects estimand.

**Verified, not assumed.** On the adoption margin, where both are estimable:
correlation between FE and Mundlak coefficient vectors **0.9999**, median
absolute difference **3.0%**. Mundlak also retains the 1,092 counties (4,656
tracts) that FE must drop for having no within-county outcome variation.

**Recommended structure going forward:** use true fixed effects for the
adoption margin (`fixest::feglm` handles it), Mundlak only for intensity where
it is forced, and report the 0.9999 comparison as the bridge. This is a
stronger position than using Mundlak in both.

### A mistake to avoid

Fitting an ordinary negative binomial to the positive subsample (e.g.
`fenegbin` on `filter(d, y > 0)`) is **a misspecification, not an
approximation**. The second hurdle margin is zero-truncated. On this data the
error attenuates every slope by roughly half and biases theta 5x (renter share
0.93 vs 1.42; theta 2.79 vs 0.53).

---

## 7. Results so far, in brief

Both margins, tract level, with county controls:

**Land use dominates.** `employment_ratio` is the largest coefficient in both
margins (2.00 adoption, 1.68 intensity), `pct_jobs_retail_food` next.

**Income differs by margin.** Null on adoption once county is controlled
(0.029, n.s.); positive and significant on intensity (0.209).

**Poverty is the mirror image.** Null on adoption (0.101, n.s.), strongly
positive on intensity (0.596).

**Race shrinks sharply under county controls.** `pct_black` 0.989 -> 0.495
(adoption), 0.626 -> 0.185 (intensity). Most apparent racial patterning is
between-county.

**Exposure and land use separate zero from camera tracts an order of magnitude
better than socioeconomics**: road density 1.77x, arterial km 1.54x,
employment ratio 1.29x, versus median income 1.01x and poverty 0.99x.

---

## 8. Re-running at a different aggregation

Every dataset exists at all four levels. To move from tract to, say, place:

1. Read `external/data/model_frame_place.parquet` instead of the tract file.
2. Swap the key column: `place_geoid` rather than `tract_geoid`.
3. **Re-check the scale block.** The `{log_pop, log_area}` recommendation is
   specific to tracts. Places and counties vary far more in population
   (sd(log pop) 1.92 and 1.51 versus 0.51 at tract), so density may no longer
   be nearly collinear with area. Re-run the VIF check before trusting it.
4. **County effects are only exact at tract level.** `tract_geoid[1:5]` is the
   county FIPS. Place and ZCTA are assigned to counties by centroid and can
   cross county lines.
5. Expect different zero shares: tract 54.0%, place 74.3%, county 29.8%,
   ZCTA 60.2%.

The table scripts take the level as a small edit at the top; the model scripts
similarly.

---

## 9. Known issues and things already fixed

Bugs found and corrected during the build, recorded so they are not
reintroduced:

- **Road double-counting.** Census boundaries are often drawn down the middle
  of major roads, so a plain overlay credited such a road to both adjacent
  polygons — inflating tract road mileage by 26%. Corrected by shrinking each
  polygon 1m inward and halving boundary-lying length. Totals now reconcile to
  raw TIGER at 1.0000.
- **Vendor undercount.** Reading only `manufacturer` missed 744 California
  cameras tagged `brand=Flock Safety`. The undercount ranged 0.01% (FL) to 36%
  (VA) — non-random across geographies. Use the coalesced `vendor` column.
- **Overpass mirrors serve stale data.** `kumi.systems` returned 1,526
  Pennsylvania nodes against the primary's 2,347. Endpoint provenance is now
  recorded and mirror-sourced states are retried.
- **Crime attributed to police station location.** Crediting a city's crime to
  the tract holding its station gave 8.6% tract coverage; aggregating to
  jurisdiction and broadcasting down gives 89.3%.
- **GEOIDs as floats** in the supplied CSV. California codes lost their leading
  zero. Always read as character.

### Open limitations

- **Crime does not vary within county**, so it cannot be identified alongside
  county effects. Using it requires dropping to state effects.
- **Road measure is arterials only** (TIGER S1100+S1200). Local streets
  (S1400) are excluded — per-county files, ~21GB.
- **Alaska has no LODES data** in any year and is excluded from land-use
  measures. Michigan uses the 2021 vintage (no 2022 release).
- **National ohsome history not yet run.** This is the mapping-effort
  denominator that would let us bound the discovery bias. ~3,100 county
  polygons, roughly an hour.
- **Crime fetch had a 10.4% agency failure rate**, clustered by state (CT 65%,
  CO 57%, KY 39%, NY 38%, NC 32%) — known UCR participation gaps, not a bug.

---

## 10. File map

```
flock_alpr/              pipeline package
  config.py              paths, endpoints, state lists
  http.py                cached, backoff-retrying fetch
  extract_osm.py         Overpass camera nodes
  extract_osm_history.py ohsome discovery series
  extract_aos.py         Atlas of Surveillance
  geocode.py             spatial joins, TIGER shapes
  covariates.py          ACS + FBI crime
  roads.py               arterial road exposure
  landuse.py             LODES jobs/residents
  build_panel.py         panel assembly
  cli.py                 python -m flock_alpr <stage>

external/                analysis on the supplied snapshot
  build_multilevel_panels.py   builds model_frame_<level>
  build_camera_dataset.py      builds camera_dataset
  build_tract_model_frame.py   tract frame from the CSV
  hurdle_pscl.R                simple pscl hurdle
  hurdle_fe.R                  Mundlak hurdle (recommended)
  hurdle_tract_final.R         glmmTMB truncated NB
  table_adoption_ladder.R      5-column specification table
  table_intensity_ladder.R     5-column specification table
  fig_count_distribution.R     Figure 1
  descriptives_count.R         count descriptives
  load_camera_dataset.R        R loader
  data/                        outputs

docs/
  modeling_section.tex         paper section, model strategy
  model_specification.tex      the equations
  table_variable_list.tex      variable inventory
  table_adoption_ladder.tex    generated table
  table_intensity_ladder.tex   generated table
  covariate_table.tex          full variable inventory
  road_exposure.md             road measure documentation
  landuse.md                   land use documentation

tests/                   79 tests, network-free
```

---

## 11. Environment

Python 3.10 in `.venv` (pandas, geopandas, pyarrow, requests).
R 4.3.1 with `arrow`, `dplyr`, `fixest`, `glmmTMB`, `pscl`, `stargazer`,
`ggplot2`.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest          # 79 tests, no network needed
```

API keys needed only to rebuild covariates from scratch:
`CENSUS_API_KEY` (api.census.gov/data/key_signup.html) and
`FBI_API_KEY` (api.data.gov/signup). The assembled data is included, so
neither is required to re-run models.
