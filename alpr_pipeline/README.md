# ALPR Camera Location Pipeline

Collects Flock Safety (and every other vendor's) ALPR camera locations into a
SQLite database and flat files — CSV, Parquet, GeoJSON, Excel — for research use.

---

## 1. Where DeFlock's ALPR data actually comes from

Short answer: **OpenStreetMap**. DeFlock does not run its own camera database.
Every downstream product is a cache or reprojection of one OSM query.

The defining tag pair, a crowdsourced convention DeFlock standardized and
documents at [deflock.org](https://deflock.org):

```
man_made       = surveillance
surveillance:type = ALPR
```

Anyone can add a camera through the DeFlock app or OSM's iD editor; it enters
the global OSM database and flows to every consumer below.

### The chain

```
                  Volunteers (DeFlock app / OSM iD editor)
                                  │
                                  ▼
                    OpenStreetMap database (ODbL)
                                  │
                     Overpass API (3 mirrors)
                     overpass.deflock.org
                     overpass-api.de
                     overpass.kumi.systems
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
  AWS Lambda              Cloudflare Worker          this pipeline
  "alpr_cache"            "flockhopper-data"         (direct query)
  hourly (STALE)          daily 09:00 UTC
         │                        │
         ▼                        ▼
  cdn.deflock.me/          R2 → data.dontgetflocked.com
    regions/{lat}/{lon}      cameras.geojson.gz     (US)
    .json                    cameras-ca.geojson.gz  (CA)
    alpr-counts.json                │
         │                          ▼
         │                  tiles.dontgetflocked.com
         │                    cameras-{us,ca}-hourly.pmtiles
         ▼                          ▼
    deflock.org               maps.deflock.org
```

### Repository evidence

| Claim | Source |
|---|---|
| Tag pair defines an ALPR | `serverless/alpr_cache/src/alpr_cache.py:47-49` (Overpass QL) |
| Hourly counts come from Overpass | `serverless/alpr_counts/src/alpr_counts.py:8-15` |
| Legacy map reads 20° region tiles | `webapp/src/stores/tiles.ts:8` |
| Modern pipeline is a Cloudflare Worker | `deflockhopper_maps/worker/wrangler.toml` |
| Adaptive tiling + mirror fallback | `deflockhopper_maps/worker/src/fetchers/cameras.ts`, `worker/src/lib/overpass.ts` |
| Published attribute whitelist | `worker/src/fetchers/cameras.ts` (`addElementsToFeatures`) |

### Why the modern pipeline tiles its queries

A single US-wide `out meta` query now returns ~107k elements / ~54MB and runs
right at Overpass's 60-second gateway ceiling, so it times out unreliably. The
Worker instead probes a grid with cheap `out count` queries, recursively
quarters any cell over ~5,000 cameras, and fetches only the leaves. This
pipeline's `harvest` module generalizes that from US-only to worldwide.

### Two things worth knowing before you cite this data

**It is crowdsourced, not a registry.** Coverage is uneven and reflects where
volunteers have mapped, not where cameras exist. Absence of cameras in a county
is not evidence of absence of cameras. Treat counts as a lower bound.

**A small number of records are mistagged.** The dataset contains 28 OSM *ways*
alongside ~135k nodes, and some carry road attributes (`ref=US 29;GA 8`,
`start_date=1923`) that clearly describe the highway rather than the camera.
The pipeline keeps them, flagged by `osm_type='way'`, so you can filter them out:
`WHERE osm_type = 'node'`.

### Superseded / dead endpoints

* `cdn.deflock.me/flock_cameras_null.json` — referenced at
  `webapp/src/services/apiService.ts:80`, now returns **HTTP 403**. Dead.
* `serverless/alpr_clusters` — marked deprecated in the README.
* `deflock-clusters.s3.amazonaws.com/*.csv` — leaked-document artifacts linked
  from the site's content pages, unrelated to the camera location feed.

---

## 2. Install

```bash
# from the repo root (~/flock-analysis)
python3 -m venv .venv
.venv/bin/pip install -r alpr_pipeline/requirements.txt
```

The 1 GB `data/` directory (SQLite DB, exports, covariate cache, panels) is
**not** in git. On Alex's machine `alpr_pipeline/data` is a symlink to
`~/flock_research/alpr_pipeline/data`; elsewhere, re-create it by running the
`fetch` and `covariates` commands below (≈30 min including downloads).

## 3. Usage

All commands run from `alpr_pipeline/`.

```bash
PY=../.venv/bin/python

# Fast path — one HTTP request per country, no load on Overpass. Recommended
# for routine refreshes. This is what you want most of the time.
$PY -m alpr_pipeline fetch --source derived --countries US CA --export

# Full path — queries Overpass directly with adaptive tiling. Slower but
# returns the COMPLETE raw OSM tag set plus changeset IDs and editor
# usernames, which the derived feeds strip. Needed for the n_mappers control.
$PY -m alpr_pipeline fetch --source overpass --region us --export

# Worldwide. Heavier and more failure-prone — see the seed-cell note below.
$PY -m alpr_pipeline fetch --source overpass --region world

# Scope a harvest to one bounding box (S W N E) — good for testing
$PY -m alpr_pipeline fetch --source overpass --bbox 39.5 -105.5 40.5 -104.5

# Third source, independent producer — useful as a cross-check
$PY -m alpr_pipeline fetch --source deflock-regions

# Export from the DB without re-fetching
$PY -m alpr_pipeline export --flock-only --format csv parquet xlsx

# Stats, and a drift check against live upstream counters
$PY -m alpr_pipeline summary
$PY -m alpr_pipeline verify
```

### Choosing a source

| | `derived` | `overpass` | `deflock-regions` |
|---|---|---|---|
| Requests | 1 per country | ~200 | ~40 |
| Runtime | seconds | 15–40 min | ~1 min |
| Coverage | US + CA | worldwide | worldwide |
| Full raw OSM tags | ✗ | ✓ | partial |
| Changeset / editor | ✗ | ✓ | ✗ |
| Wikidata vendor Q-IDs | ✗ | ✓ | partial |
| Freshness | daily 09:00 UTC | live | **stale — see below** |

> **The `deflock-regions` feed has stopped updating.** Its Lambda is configured
> for hourly rebuilds (`UPDATE_RATE_MINS` defaults to `rate(60 minutes)`), but
> as of 2026-08-04 15:17 UTC `cdn.deflock.me/regions/index.json` carried a
> `Last-Modified` of 2026-08-03 04:39 UTC — roughly 35 hours stale. The sibling
> `alpr-counts.json` on the same CDN was 30 minutes old, so the CDN is fine and
> the region-tile job specifically is not running. Treat this source as a
> historical cross-check, not a live feed, and re-check its `Last-Modified`
> before relying on it.

### Overpass seed cells are a hard constraint, not a tuning knob

A worldwide run seeded with 30° cells **fails**: an `out count` probe over a
cell containing the US east coast is expensive enough that all three mirrors
return 504 or time out, and the run aborts after ~25 minutes. It fails *closed*
— nothing partial is written — but you get no data.

`--region us` (the default) uses the reference implementation's proven
6.5° × 9.84° cells over the lower 48 plus AK/HI/PR. `--region world` grids the
globe at `--seed-step` degrees; keep that at **10 or below**.

**Please prefer `derived` unless you need raw tags.** Overpass is donated
infrastructure. The client throttles to 1 request/second and identifies itself;
set `--user-agent` to include your own contact address before running large
harvests.

### Mixing sources is safe

You can run an `overpass` harvest once for the full tag set, then keep the DB
fresh with cheap `derived` runs. A partial source never overwrites a stored
value with NULL — it only fills gaps and advances `last_seen_snapshot`. A
`complete` source (Overpass) *does* overwrite, so a tag genuinely deleted from
OSM is cleared rather than lingering forever. See `store.write_records`.

### Testing

```bash
$PY tests/test_normalize.py    # direction parsing + vendor classification
$PY tests/test_store.py        # snapshot/upsert semantics
$PY tests/test_covariates.py   # ACS measure definitions + panel construction
```

---

## 4. Output

`data/alpr.sqlite` plus, on `--export`:

| File | Notes |
|---|---|
| **`alpr_cameras_us.parquet`** | **Master for US analysis** — all vendors, US only |
| `alpr_cameras_us.{csv,xlsx,geojson}` | Same rows, other formats |
| `flock_cameras_us.*` | US, Flock only (`--country US --flock-only`) |
| `alpr_cameras.*` | Everything in the DB — includes CA and MX rows |
| `flock_cameras.*` | Flock only, all countries |

Parquet is the one to reach for in pandas: ~4x smaller than the CSV, and it
preserves types so `osm_id` stays an integer and nulls stay null. Excel drops
`tags_json` (it exceeds the 32,767-char cell cap).

```bash
# The US master, both variants
$PY -m alpr_pipeline export --country US --format csv parquet xlsx geojson
$PY -m alpr_pipeline export --country US --flock-only --format csv parquet xlsx
```

**Filter by country, not by feed.** `country_code` is assigned per point from
boundary geometry, so it is the reliable US filter. The publisher's US feed is
built by tiling a US grid and subtracting neighbours *by node ID*, which leaves
a residue behind: 48 rows in it are geographically in Mexico and 13 more in
Canada. `--country US` excludes them; trusting the feed name would not.

### Schema

`cameras` — one row per camera, current state:

| Column | Meaning |
|---|---|
| `osm_type`, `osm_id` | OSM identity; composite primary key. Cite as `https://openstreetmap.org/{osm_type}/{osm_id}` |
| `lat`, `lon` | WGS84, 7 dp. Ways get a centroid of their child nodes |
| `country_code`, `state` | Offline point-in-polygon (Natural Earth 10m) |
| `brand_raw`, `manufacturer_raw`, `operator_raw` | Verbatim OSM tag values |
| `brand_wikidata`, `manufacturer_wikidata`, `operator_wikidata` | Wikidata Q-IDs from `*:wikidata` tags — unambiguous vendor identity |
| `vendor` | Normalized from free text: `Flock Safety`, `Motorola Solutions`, … |
| `vendor_wikidata` | Vendor label resolved from the Q-ID (`overpass` source only) |
| `is_flock` | 1 if brand/manufacturer/operator **or** a Wikidata Q-ID identifies Flock |
| `direction_deg` | Bearing, 0–360, N=0. Parsed from cardinals, ranges, bound notation |
| `direction_count`, `directions_all` | Multi-lens gantries encode several bearings |
| `surveillance_zone`, `mount_type`, `camera_type`, `support`, `height` | Deployment context |
| `ref`, `start_date`, `operator_type`, `description`, `note`, `website` | Assorted OSM tags |
| `osm_version`, `osm_timestamp`, `osm_changeset`, `osm_user`, `osm_uid` | Edit provenance (`overpass` source only) |
| `tags_json` | **Complete** raw tag dict as JSON (`overpass` source only) |
| `first_seen_snapshot`, `last_seen_snapshot` | Longitudinal tracking |

`snapshots` — one row per run: timestamps, source, endpoint, counts, and
`osm_base_utc`, the OSM database timestamp the data was cut from.

`observations` — one row per camera per snapshot. This is what makes the
dataset longitudinal rather than a point-in-time dump.

### Tracking deployment growth over time

Re-run `fetch` on a schedule. `first_seen_snapshot` is preserved across
re-runs while `last_seen_snapshot` advances, so:

```sql
-- Cameras that appeared in snapshot 5 and were not present in snapshot 4
SELECT c.* FROM cameras c
WHERE c.first_seen_snapshot = 5;

-- Cameras that vanished (present in 4, absent in 5) — removed or retagged
SELECT o.osm_type, o.osm_id, o.lat, o.lon FROM observations o
WHERE o.snapshot_id = 4
  AND NOT EXISTS (SELECT 1 FROM observations n
                  WHERE n.snapshot_id = 5
                    AND n.osm_type = o.osm_type AND n.osm_id = o.osm_id);

-- Flock camera count by state over time
SELECT s.snapshot_id, s.started_utc, c.state, COUNT(*) n
FROM observations o
JOIN snapshots s USING (snapshot_id)
JOIN cameras c ON c.osm_type = o.osm_type AND c.osm_id = o.osm_id
WHERE o.is_flock = 1
GROUP BY s.snapshot_id, c.state ORDER BY s.snapshot_id, n DESC;
```

---

## 5. Covariates for political-science research

```bash
$PY -m alpr_pipeline covariates --level tract --also-assign county place
$PY -m alpr_pipeline covariates --level county     # or place, or bg
```

Assigns each camera its census GEOIDs by offline point-in-polygon against
Census cartographic boundary files, then attaches 21 ACS 5-year measures.

### ⚠️ Read this before modelling

**The outcome is "cameras *mapped*", not "cameras *present*."** DeFlock's data
is crowdsourced, so camera counts confound actual deployment with volunteer
mapping effort. A tract with zero cameras may have none — or may simply have no
active OSM contributor. This is the dominant threat to inference here, and no
covariate fully fixes it.

Partial mitigations, in rough order of strength:

1. Restrict to areas with demonstrated mapper presence (`n_mappers > 0` in a
   containing county) so absence means something.
2. Use `n_mappers`, `first_mapped`, `last_mapped` in the panel as effort
   controls. These require an `overpass` harvest — the derived feeds strip
   editor metadata.
3. Model counts *conditional on* at least one camera, sidestepping the
   zero-inflation entirely.
4. Validate a sample against a jurisdiction with a published Flock contract or
   a transparency-portal listing, and report the coverage rate you find.

Treat every count as a **lower bound**.

### Output files

| File | Rows | Purpose |
|---|---|---|
| `tract_panel.parquet` | 85,381 | **The modelling table.** One row per tract nationwide, with `camera_count`, `flock_count`, `has_camera`, `cameras_per_10k` + covariates. Includes the 54.5% of tracts with **zero** cameras — the control observations |
| `cameras_with_covariates_tract.parquet` | 124,623 | One row per camera, its tract's covariates attached |
| `acs2023_tract.parquet` | 85,381 | The ACS reference table alone |

Swap `tract` for `county`, `place`, or `bg` in the filenames.

### Geography assignment quality

| Level | Assigned | Notes |
|---|---|---|
| Tract | 124,609 / 124,623 | 14 unassigned (offshore beyond the 2 km fallback) |
| County | 124,609 / 124,623 | Same |
| Place | 115,911 / 124,623 | 8,712 unassigned — **correct**: those cameras are in unincorporated areas belonging to no municipality |

Block group is the finest level published (242,296 units), but many detailed
tables are not released at that geography and margins of error are wide.
**Tract is the recommended default.**

### Political and crime covariates

```bash
# Anonymous: elections + ideology
$PY -m alpr_pipeline covariates --level tract --political

# Adds FBI UCR crime. DISCLOSES your identity to Harvard Dataverse.
$PY -m alpr_pipeline covariates --level tract --political --crime \
    --name "..." --email "..." --institution "..." \
    --research-question "..."
```

| Source | Level | Anonymous? | What you get |
|---|---|---|---|
| **VEST precinct-to-census reallocation** (`10.7910/DVN/Z8TSH3`) | tract, bg | ✓ | 2020 presidential vote reallocated onto census geography — a plain GEOID join, no spatial work. 82,750 of 85,381 tracts (97%) |
| **American Ideology Project** (`10.7910/DVN/BQKU4M`) | county, place | ✓ | MRP-estimated latent ideology, `mrp_ideology` + SE. 3,152 counties, 6,704 places |
| **MEDSL county returns** (`10.7910/DVN/VOQCHQ`) | county | 2000–2016 only | Seven presidential elections. The GitHub mirror is anonymous; 2020/2024 needs a guestbook |
| **FBI UCR via Kaplan** (`10.7910/DVN/OESSD1`) | agency → county, place | ✗ guestbook | Index violent/property crime + 8 sub-offences, rates per 100k. 2,899 counties |

#### On the identity disclosure

MEDSL and Kaplan's UCR sit behind Dataverse **guestbooks**. No account or token
is involved, but submitting one transmits your name, email, institution, and
free-text answers (including your research question, verbatim) to Harvard.

The code never does this implicitly. `--crime` refuses to run without the four
identity flags, and `fetch_datafile` tries an anonymous GET first, falling back
to a guestbook only if the server actually demands one. Call
`describe_guestbook(id)` to see exactly what a given form asks before
submitting. Everything else in the pipeline is anonymous.

#### Crime data caveats

* **There is no tract-level crime.** UCR is reported by *agency* (ORI), so
  county is the finest honest geography. Every tract in a county gets the same
  value — acknowledge that in your specification.
* Only **local** agencies (police departments, sheriffs, constables) are rolled
  into counties. Summing a state highway patrol into a county would
  double-count offences the local department already reported.
* Agencies reporting **fewer than 12 months are dropped**, not annualized
  (11,827 of 17,409 local agencies survive). Partial reporting is not missing
  at random; scaling it up would invent precision.
* `ucr_population` is the summed agency population, which is the right
  denominator for these rates and will not equal the tract's `pop_total`.

#### VEST 2016 is deliberately excluded

The pipeline joins **2020 only**. VEST's 2016 reallocation is built on
2010-vintage census geography: 15.6% of its tract GEOIDs do not exist in the
2020 vintage, and it matches just 71% of 2023 ACS tracts (vs 97% for 2020).
Differencing the two to get a "swing" would measure boundary redefinition as
much as political change. `fetch_vest_reallocated(..., year=2016)` still works
if you have a crosswalk and want to handle it yourself; it logs a warning.

### The 21 ACS measures

Population, median age · median household income, per-capita income, Gini ·
% White / Black / American Indian / Asian / two-or-more / Hispanic · % foreign
born · % below poverty · % bachelor's or higher · % unemployed · % renter
occupied · median home value, median gross rent · % no vehicle · % drove alone,
% public transit.

Column numbering was verified against the live 2023 files, not assumed — ACS
renumbers tables between vintages, and a shifted index yields plausible-looking
garbage. Rates divide by each table's **own universe** (B17001's is "population
for whom poverty status is determined", B23025's is the civilian labour force),
never by total population.

**Watch for ACS top-codes**: `median_hh_income = 250001` means "≥ $250,000",
`median_home_value = 2000001` and `median_gross_rent = 3501` likewise. They are
not real values and will distort a regression if treated as continuous.
Negative jam codes (−666666666 = "not available") are already converted to
NULL. Null rates run 1–6%, mostly zero-population tracts (parks, water,
industrial) — note tract `48439980000` has 54 cameras and a population of 0.

### Why bulk files instead of the Census API

As of 2026 the Census API redirects every un-keyed request to a "Missing Key"
page, so an API-based pipeline cannot run unattended. The table-based summary
files at `www2.census.gov` need **no key**, carry every geography, and are
streamed and reduced on the fly (B17001 alone is 113 MB raw).

## 6. Data quality notes

* **`vendor` vs `is_flock` can disagree, by design.** `vendor` takes brand as
  most authoritative; `is_flock` is true if *any* of brand/manufacturer/operator
  names Flock. One node carries `brand=Neology, Inc.` with
  `operator=Flock Safety` — Flock-operated, Neology-built. Both columns are
  right; pick the one that matches your research question.
* **Unclassified vendors (~7k rows)** have no brand tag at all, or a placeholder
  (`unknown`, `yes`). They are not "not Flock" — they are unknown.
* **The two vendor columns cross-validate each other.** On an `overpass`
  harvest, `vendor` (free-text regex) and `vendor_wikidata` (Q-ID lookup) agreed
  on 100% of records where both were present in spot checks. Where they
  disagree, trust `vendor_wikidata` — a Q-ID is an identifier, a brand string is
  a typo waiting to happen. Confirmed Q-IDs seen in the data: Flock Safety
  `Q108485435`, Motorola Solutions `Q634815`, Leonardo `Q910379`.
* **Bridges and barrier islands** fall outside land polygons. State assignment
  falls back to the nearest boundary within ~0.15° (~16 km), which recovers
  toll-bridge cameras (Bay Area Toll Authority, Golden Gate) without snapping
  genuinely offshore points to an arbitrary state.
* **US territories** (PR, VI, GU, AS, MP) are normalized to `country_code='US'`
  with the territory code in `state`.
* **Counts drift** between sources: they are cut at different times from a
  database that changes continuously. `verify` warns above 10% drift.

## 7. Licensing

Camera data is **© OpenStreetMap contributors, licensed ODbL**. ODbL is a
share-alike licence: if you publish a derived database you must attribute OSM
and release the derived database under ODbL. Attribution is required in any
publication. Boundary files are public domain (Natural Earth).
