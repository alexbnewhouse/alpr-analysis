# CLAUDE.md

Agent context for the ALPR adoption study. Read `HANDOFF.md` for the full
research narrative; this file is the operational contract.

## What this is

Modelling where automatic license plate readers (ALPRs) are located across the
US, at Census tract / place / county / ZCTA. Outcome is a camera count per
geographic unit. Two-part hurdle: adoption (any camera) and intensity (how
many, given at least one).

## Environment

Python lives in `.venv` — **never use the system or anaconda interpreter.**

```bash
.venv/bin/python -m pytest -m "not network"   # 79 tests, no network needed
.venv/bin/python -m flock_alpr <stage>        # osm|aos|geocode|history|covariates|panel
Rscript external/<script>.R                   # all analysis is R
```

R 4.3.1 with `arrow`, `dplyr`, `fixest`, `glmmTMB`, `pscl`, `stargazer`,
`ggplot2`. Data is Parquet; R reads it with `arrow::read_parquet`.

API keys are only needed to rebuild covariates from source. The assembled data
is committed, so models run without them.

## Invariants — violating these silently corrupts results

**GEOIDs are character, always.** `tract_geoid` (11), `place_geoid` (7),
`county_fips` (5), `zcta` (5). Read as numeric and every state with FIPS below
10 loses its leading zero and mis-joins — CA, AL, AK, AR, CO, CT, DE, DC, FL,
GA. This has already bitten once in a supplied CSV.

**Never filter to camera-bearing units before modelling.** The
`model_frame_*.parquet` files deliberately include units with zero cameras.
Dropping them conditions on the outcome and overstates the mean count by 2.2x.

**Use `vendor`, never `manufacturer`, to identify Flock.** `vendor` coalesces
`manufacturer` → `brand` → `surveillance:manufacturer` → `surveillance:brand`.
Reading `manufacturer` alone undercounts Flock by 0.01% (FL) to 36% (VA) —
non-random across geographies.

**OSM-derived counts over time are named `discovery_count`, never
`installed_count`.** They measure when a volunteer *mapped* a camera, not when
it was installed. A test in `tests/test_extract_osm_history.py` fails the build
if the banned name appears as a column.

**Crime is a jurisdiction-level quantity.** It does not vary within a county.
Do not attach it to a point location; do not expect it to be identified
alongside county fixed effects.

## Modelling constraints

**Scale block collinearity.** `log_density` is exactly `log_pop - log_area`.
All three cannot enter. At tract level use `{log_pop, log_area}` (VIF 1.3 and
4.9); `{log_area, log_density}` gives 18.5 and 26.6, because tracts are built
to hold ~4,000 people so density is nearly `-log_area` (r = -0.972).
**This is tract-specific — re-run the VIF check at other levels.**

**Centre log density before squaring.** Uncentred VIF 22, centred 1.8.

**`pct_white` is the omitted reference** — race shares are compositional.
**Never enter owner and renter share together** — exact complements.

**Do not add these** (r > 0.69 with income, same latent factor): per-capita
income, median home value, median gross rent, `pct_bachelors_plus`.

**Do not add these** (bad controls — consequences of urban form that steal the
density coefficient): `pct_no_vehicle`, `pct_drove_alone`, `pct_public_transit`.

**Operator/owner cannot be a right-hand-side control.** It is undefined for
zero-camera units and post-treatment for the rest. Split the outcome
(`n_police`, `n_retail`) instead.

## The intensity margin is zero-truncated

The second hurdle margin is a **zero-truncated** negative binomial. Fitting an
ordinary NB to `filter(d, y > 0)` — e.g. `fenegbin` on the positive subsample —
is a misspecification, not an approximation. It attenuates every slope by
roughly half and biases theta 5x.

Tooling reality:

| | truncated NB | many fixed effects |
|---|---|---|
| `pscl` | yes | no |
| `fixest` | no | yes |
| `glmmTMB` | yes | random effects only |

Hence **Mundlak correlated random effects** for intensity: county random
intercept plus the county mean of every covariate, which recovers the
fixed-effects estimand. Verified against true FE on the adoption margin:
correlation 0.9999, median difference 3.0%.

The adoption margin is just a logit, so `fixest::feglm` can use true county
fixed effects there. Preferred structure: **FE for adoption, Mundlak only for
intensity.**

## Layout

```
flock_alpr/         pipeline package (extract, geocode, covariates, roads, landuse)
external/           analysis scripts (R) + data/ outputs
  hurdle_fe.R              Mundlak hurdle (recommended)
  hurdle_pscl.R            simple pscl hurdle, no geography
  table_*_ladder.R         5-column specification tables
  build_multilevel_panels.py  rebuilds model_frame_<level>
docs/               LaTeX sections and tables, methodology notes
tests/              79 network-free tests against committed fixtures
data/interim/       ACS, roads, landuse, crime by level
```

## Conventions

Network fetches cache to `data/raw/cache/` keyed by request hash — re-running
is free, and a parser bug never costs another API call. Pass `force=True` to
bypass.

Parser tests run against committed fixtures and never hit the network. Live-API
tests are marked `network` and deselected by default.

Nothing under `data/` is committed.

## When editing LaTeX tables

stargazer puts notes in an unbreakable `\multicolumn` row inside the tabular,
so a long note sets the width of the whole table. Keep the note short and put
the real one in a `minipage` below. Also set `dep.var.labels.include = FALSE`
when models are built from a formula-constructing helper — stargazer otherwise
deparses the call into the header and adds ~330pt of literal R code.

Verify tables by compiling them, not by eye:

```bash
pdflatex -interaction=nonstopmode file.tex | grep -c "Overfull"
```

## Things already fixed — do not reintroduce

- **Road double-counting.** Census boundaries often run down the middle of
  major roads, so a plain overlay credits a road to both adjacent polygons
  (+26% at tract level). `roads.py` shrinks each polygon 1m inward and halves
  boundary-lying length. Totals reconcile to raw TIGER at 1.0000.
- **Overpass mirrors serve stale data.** kumi.systems returned 1,526
  Pennsylvania nodes against the primary's 2,347. `source_endpoint` is recorded
  per state and mirror-sourced checkpoints are retried against the primary.
- **Crime attributed to station coordinates** gave 8.6% tract coverage;
  aggregating to jurisdiction and broadcasting down gives 89.3%.
- **State-level extract failures** used to discard all prior states. Each state
  now checkpoints to its own parquet and failures are reported, not fatal.
