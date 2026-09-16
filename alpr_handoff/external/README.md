# External dataset track

Analysis built from the supplied `alpr_cameras_us.xlsx` snapshot, kept separate
from the live-OSM pipeline in `flock_alpr/`. Only the geocoding helpers are
shared, so the spatial join is identical and the two tracks are directly
comparable.

```bash
python external/build_external_panels.py
```

```
external/
  source/alpr_cameras_us.xlsx    input snapshot (gitignored, 19 MB)
  build_external_panels.py       loader + geocoder + panel builder
  data/                          outputs (gitignored)
```

## What's in the source file

124,623 rows, 40 columns, 53 state codes (includes PR and VI). 103,865 flagged
`is_flock`. OSM timestamps span 2017-04-15 to 2026-08-03.

**18 of the 40 columns are entirely empty** and are dropped on load:
`manufacturer_raw`, `brand_wikidata`, `manufacturer_wikidata`,
`operator_wikidata`, `vendor_wikidata`, `surveillance_kind`, `camera_type`,
`support`, `height`, `operator_type`, `description`, `note`, `website`,
`wikimedia_commons`, `osm_changeset`, `osm_user`, `osm_uid`, `tag_count`.

Two consequences worth knowing:

- `osm_user` / `osm_uid` / `osm_changeset` being empty means this file **cannot**
  support mapper-level analysis of the observation bias. The live pipeline's
  ohsome `contributors` series remains the only handle on that.
- `operator_type` being empty means the police-vs-retail split (a serious
  confound — Lowe's and Home Depot operate ALPRs across hundreds of places)
  can only be approximated here from `operator_raw`, which is 82.3% null.

Territories (PR, VI — 207 rows) are excluded from the panels, since TIGER
state files and most ACS/UCR products don't cover them. They remain in the
camera-level table.

## Comparison with the live extract

| | xlsx snapshot | live Overpass extract |
|---|---|---|
| Rows | 124,623 | 125,192 |
| Flock | 103,865 | 103,529 |
| Shared osm_ids | 124,227 | 124,227 |
| Unique to it | 396 | 965 |

Same underlying OSM data, captured at slightly different moments.

## Panels produced

| Level | Units | Median | Singletons | ~Zeros | Nests in county |
|---|---|---|---|---|---|
| **tract** | 38,840 | 2 | 35.5% | 54% | **yes** |
| zcta | 13,450 | 5 | 20.8% | 60% | no |
| place | 8,242 | 4 | 26.2% | 58% | no |
| county | 2,272 | 12 | 8.5% | 28% | — |

Assignment rates: tract 100.0%, county 100.0%, ZCTA 99.9%, place 80.7%. Tracts
and counties tile the country completely; places do not, so ~19% of cameras sit
outside any incorporated place.

## Reading the table above

Tract is the primary unit because it nests in county — the 38,840 tracts map to
2,272 counties, so county fixed effects are available. ZCTAs do not nest in
anything, which is the single biggest reason not to make them the headline unit.

The tradeoff is that tract has *more* singletons (35.5%) than ZCTA (20.8%),
because tracts are smaller. That is not an argument for ZCTA: it means the
outcome is sparse and overdispersed at tract level, so model it with a negative
binomial (or zero-inflated) count model with a population offset, not OLS on
raw counts. Aggregating up to ZCTA to hide the sparsity trades a modelling
problem for an identification problem.

Report results at two scales. Given zero-inflation of 54-60% at the fine scales,
a result that only survives at one aggregation is not a result.
