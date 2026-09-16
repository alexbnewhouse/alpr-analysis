# Road exposure variable

## What it is

Kilometres of **arterial roadway** inside each geographic unit, split by road
class, plus road density per km² of land.

| Column | Definition |
|---|---|
| `road_km_primary` | Km of MTFCC **S1100** (primary road) inside the unit |
| `road_km_secondary` | Km of MTFCC **S1200** (secondary road) inside the unit |
| `road_km_arterial` | Sum of the two |
| `road_density_km_sqkm` | `road_km_arterial ÷ land_area_sqkm` |
| `has_arterial` | Indicator, `road_km_arterial > 0` |

Units with no arterial road get **0, not missing**. An absence of highway is an
observed value, not an unobserved one.

## Why it belongs in the model

ALPR cameras are mounted beside roads and read passing plates. The quantity
that creates an *opportunity* for a camera is roadway, not residents. Without
it, the socioeconomic coefficients partly measure road geometry: arterial
corridors run through commercial and lower-income areas, so income and road
exposure are correlated, and omitting one loads onto the other.

The data already says population is the wrong exposure measure. Fitting camera
counts with `offset(log(population))` imposes an elasticity of 1; the freely
estimated elasticity is about **0.25**. That gap is what this variable is for.

## Source

US Census Bureau, **TIGER/Line Shapefiles 2024, "Primary and Secondary Roads"**,
published one file per state:

```
https://www2.census.gov/geo/tiger/TIGER2024/PRISECROADS/tl_2024_<SS>_prisecroads.zip
```

Roads are classified by **MTFCC** (MAF/TIGER Feature Class Code):

| Code | Class | What it covers |
|---|---|---|
| **S1100** | Primary road | Limited-access highways — interstates and equivalent, with interchanges rather than at-grade intersections |
| **S1200** | Secondary road | Main arteries — US and state highways, county roads, multi-lane surface streets connecting towns |

Native CRS is EPSG:4269 (NAD83 geographic).

## What is deliberately excluded

**Local neighbourhood streets (MTFCC S1400) are not included.** They exist only
in TIGER's per-county "All Roads" product — 3,233 files, roughly 21 GB — and
they are the class least likely to carry a fixed ALPR.

This is a scope decision and should be stated in the paper: the measure is
**arterial exposure, not total roadway**. A dense residential tract with many
local streets but no highway will score low, correctly for the purpose of
predicting ALPR placement, but it is not a general measure of road supply.

## Method

1. **Download** the per-state primary/secondary roads shapefile.
2. **Reproject** roads and target polygons to **EPSG:5070** (NAD83 / Conus
   Albers), an equal-area conic projection in metres.
   *Length must not be computed in degrees.* A degree of longitude is about
   85 km in Florida and 65 km in Montana, so unprojected lengths are wrong,
   and wrong differently by latitude — which would correlate with region and
   contaminate the estimates.
3. **Overlay** roads on polygons with a geometric intersection, not a
   containment join, so a road crossing a boundary is split and each unit is
   credited only the length physically inside it.
4. **Correct for boundary-lying roads** (see below).
5. **Sum** segment lengths per unit by MTFCC class; convert metres to km.
6. **Divide** by TIGER land area (`ALAND`, water excluded) for density.

Units near a state line can appear in two states' road files; the per-state
results are summed, and because each state's file is clipped to its own
boundary this adds the two portions rather than double-counting.

### The boundary correction

Census boundaries are routinely drawn **down the middle of major roads**. Such
a road lies on the shared edge of two closed polygons, so a plain intersection
overlay credits its full length to *both* neighbours.

This is not a rare edge case. A verified example: North Carolina road
`110217384288` is 7.191 km long; its seven tract pieces sum to 14.382 km; the
union of those pieces is 7.191 km. Every metre was double-counted.

Left uncorrected the inflation scales with boundary density — roughly **+26% at
tract level, +6% at ZCTA, ~0% at county**. Because the bias grows as units
shrink, the measure would not be comparable across geographies, which is fatal
for a multi-scale design.

**Correction.** Each polygon is shrunk inward by 1 m. Road length inside the
shrunken polygon is genuinely interior and kept whole; the remainder lies
within a metre of the boundary, is shared with exactly one neighbour, and is
halved. After correction, total road length reconciles to raw TIGER length at
every level (North Carolina: 0.9998 at tract, 1.0000 at county).

Two notes on the tolerance. It is 1 m because TIGER road and boundary
geometries are digitised separately and rarely coincide exactly; 1 m absorbs
that jitter without capturing genuinely interior roads. And a road *crossing* a
boundary loses up to 2 m where it passes through the band — 0.1% on a 1 km
road, invisible at real arterial lengths.

## Validation

After the boundary correction, the aggregate reconciles exactly to the raw
source: summing all 51 state road files gives **1,689,790 km**; summing our
county-level output gives **1,689,735 km** — a ratio of **1.0000**. Tract
totals reconcile to county at **0.9994**.

| Level | Units | With arterial | Median km (of those >0) |
|---|---|---|---|
| tract | 84,415 | 78.8% | 9.2 |
| place | 32,041 | 81.3% | 7.2 |
| county | 3,235 | 96.7% | 425.3 |
| zcta | 33,791 | 90.9% | 33.8 |

ZCTA sums to 0.982 of county because ZCTAs do not tile all land; place sums to
0.298 because most US land area lies outside any incorporated place.

**Do not describe this as an FHWA arterial mileage figure.** The composition is
311,005 km of S1100 and 1,378,785 km of S1200. S1100 is close to FHWA's
Interstate-plus-principal-arterial definition, but S1200 is broader than FHWA
"arterial" — it includes county roads and major surface streets that FHWA
classifies as collectors. The measure is "TIGER primary and secondary roadway",
which is the right concept for camera siting but is not the same series.

## Geographic levels

Built at all four analysis levels, one file each:

```
data/interim/roads_tract.parquet
data/interim/roads_place.parquet
data/interim/roads_county.parquet
data/interim/roads_zcta.parquet
```

Join key is the level's usual GEOID (`tract_geoid`, `place_geoid`,
`county_fips`, `zcta`).

## Code

`flock_alpr/roads.py`

```python
from flock_alpr import roads
roads.build("tract")     # or "place", "county", "zcta"
```

## Known limitations

- **Arterials only.** No local streets (see above).
- **Road presence, not traffic volume.** Two arterials with identical length
  can carry very different traffic. Annual average daily traffic (AADT) from
  state DOTs or FHWA's HPMS would be the better exposure measure; it is not
  nationally uniform and would be a separate build.
- **2024 snapshot.** Road networks change slowly, so this is a minor issue for
  a cross-section, but it is not matched to the camera observation dates.
- **Boundary effects.** A camera on a road that forms the boundary between two
  tracts is assigned to one of them by the point-in-polygon join, while the
  road length is split between both.
