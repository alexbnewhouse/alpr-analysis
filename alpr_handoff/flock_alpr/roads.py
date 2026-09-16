"""Road exposure measures from TIGER/Line primary and secondary roads.

WHAT THIS MEASURES
------------------
Kilometres of arterial roadway inside each geographic unit, split by class,
plus road density (km per km2 of land).

ALPR cameras are mounted beside roads and read passing plates, so the quantity
that creates an opportunity for a camera is roadway, not residents. Population
is a poor proxy for it: fitting the camera count with population as an offset
implies an elasticity of 1, but the freely estimated elasticity is about 0.25.
Road exposure is the variable that gap is pointing at.

SOURCE
------
US Census Bureau, TIGER/Line Shapefiles 2024, "Primary and Secondary Roads",
published one file per state:

    https://www2.census.gov/geo/tiger/TIGER2024/PRISECROADS/tl_2024_<SS>_prisecroads.zip

Roads are classified by MTFCC (MAF/TIGER Feature Class Code):

    S1100  Primary road    - limited-access highways; interstates and
                             equivalent, with interchanges rather than
                             at-grade intersections
    S1200  Secondary road  - main arteries; US and state highways, county
                             roads, multi-lane surface streets connecting
                             towns

WHAT IS *NOT* INCLUDED
----------------------
Local neighbourhood streets (MTFCC S1400) are excluded. They exist only in the
per-county TIGER "All Roads" product -- 3,233 files totalling roughly 21 GB --
and they are the class least likely to carry a fixed ALPR. This is a
deliberate scope decision and should be stated in the paper: the measure is
*arterial* exposure, not total roadway.

METHOD
------
1. Download the per-state primary/secondary roads shapefile (EPSG:4269).
2. Reproject roads and target polygons to EPSG:5070 (NAD83 / Conus Albers),
   an equal-area conic projection in metres. Length must not be computed in
   degrees -- a degree of longitude is ~85 km in Florida and ~65 km in
   Montana, so unprojected lengths are wrong and wrong by latitude.
3. Overlay roads on the polygons (intersection), so a road crossing a
   boundary contributes only the portion inside each unit.
4. Sum segment lengths per unit, convert metres to kilometres.
5. Divide by land area to get density.

Units with no arterial road receive 0, not missing: an absence of highway is
a real value, not an unobserved one.
"""
import geopandas as gpd
import pandas as pd

from . import config, http

PRISEC_URL = (
    "https://www2.census.gov/geo/tiger/TIGER2024/PRISECROADS/"
    "tl_2024_{fips}_prisecroads.zip"
)

# Equal-area conic in metres; correct for length and area across the US.
EQUAL_AREA_CRS = "EPSG:5070"

MTFCC_LABELS = {"S1100": "primary", "S1200": "secondary"}

# Half-width, in metres, of the band around a polygon boundary within which a
# road is treated as lying ON the boundary and therefore shared with the
# neighbouring unit. TIGER road and boundary geometries are digitised
# separately, so an exact match is rare; 1 m absorbs that jitter without
# capturing genuinely interior roads.
BOUNDARY_TOL_M = 1.0


def load_state_roads(state: str) -> gpd.GeoDataFrame:
    """Primary and secondary roads for one state, projected to metres."""
    fips = config.STATE_FIPS[state]
    dest = config.TIGER_DIR / f"prisec_{fips}.zip"
    if not dest.exists():
        dest.write_bytes(http.fetch(PRISEC_URL.format(fips=fips), timeout=900))
    gdf = gpd.read_file(f"zip://{dest}", columns=["LINEARID", "MTFCC", "geometry"])
    return gdf.to_crs(EQUAL_AREA_CRS)


def _share_boundary_roads(clipped: gpd.GeoDataFrame, polys: gpd.GeoDataFrame,
                          key: str) -> gpd.GeoDataFrame:
    """Split the credit for roads that run along a shared polygon boundary.

    Census boundaries are routinely drawn down the middle of major roads, so a
    large share of arterial mileage lies exactly ON a boundary. Such a road
    belongs to both adjacent closed polygons, and an intersection overlay
    returns it once per neighbour. Verified case: NC road 110217384288 is
    7.191 km long, its seven tract pieces sum to 14.382 km, and the union of
    those pieces is 7.191 km -- every metre double-counted.

    Uncorrected this inflates totals in proportion to boundary density: about
    +26% at tract level, +7% at ZCTA, ~0% at county. Because the bias grows as
    units shrink, the measure would not be comparable across geographies.

    Matching identical geometries does not work -- the two clips are
    geometrically equal but not byte-identical. Testing a single representative
    point per piece is also insufficient: it misses pieces that run along a
    boundary for part of their length and through the interior for the rest.

    Instead each polygon is shrunk inward by a small tolerance. Length inside
    the shrunken polygon is genuinely interior and is kept whole; the remainder
    lies within a tolerance of the boundary, is shared with exactly one
    neighbour, and is halved. This is an elementwise operation against each
    piece's own polygon -- unioning all boundaries nationally does not finish
    in reasonable time.
    """
    shrunk = (polys.set_index(key).geometry
              .buffer(-BOUNDARY_TOL_M)
              .reindex(clipped[key].values))
    interior = gpd.GeoSeries(clipped.geometry.values, crs=clipped.crs).intersection(
        gpd.GeoSeries(shrunk.values, crs=polys.crs), align=False
    ).length.values / 1000.0

    out = clipped.copy()
    interior = pd.Series(interior, index=out.index).clip(lower=0.0)
    on_bnd = (out["km"] - interior).clip(lower=0.0)
    out["km"] = interior + on_bnd / 2.0
    return out


def road_km_by_unit(roads: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame,
                    key: str) -> pd.DataFrame:
    """Kilometres of road inside each polygon, split by road class.

    Uses an intersection overlay rather than a containment join so that a road
    crossing a boundary is split, and each unit is credited only the length
    actually within it.
    """
    polys = polygons[[key, "geometry"]].to_crs(EQUAL_AREA_CRS)
    clipped = gpd.overlay(
        roads[["LINEARID", "MTFCC", "geometry"]], polys,
        how="intersection", keep_geom_type=True,
    )
    if not len(clipped):
        return pd.DataFrame(columns=[key, "road_km_primary", "road_km_secondary"])

    clipped["km"] = clipped.geometry.length / 1000.0
    clipped = _share_boundary_roads(clipped, polys, key)
    clipped["cls"] = clipped["MTFCC"].map(MTFCC_LABELS)
    out = (clipped.dropna(subset=["cls"])
           .pivot_table(index=key, columns="cls", values="km", aggfunc="sum")
           .reset_index())
    out.columns.name = None
    for cls in MTFCC_LABELS.values():
        col = f"road_km_{cls}"
        # A unit with secondary but no primary road gets an empty pivot cell.
        # That is zero kilometres of primary road, not an unknown quantity.
        out[col] = out.pop(cls).fillna(0.0) if cls in out.columns else 0.0
    return out[[key, "road_km_primary", "road_km_secondary"]]


def build(level: str, states=None, verbose=True) -> pd.DataFrame:
    """Road exposure for every unit at one geography level.

    Returns one row per unit with:
        road_km_primary     S1100 kilometres
        road_km_secondary   S1200 kilometres
        road_km_arterial    their sum
        road_density_km_sqkm  arterial km per km2 of land
        has_arterial        indicator, any arterial road present
    """
    from . import geocode

    key = geocode.KEYS[level][1]
    shp_states = config.STATES if level in geocode.PER_STATE else None
    polygons = geocode.load_shapes(level, states=shp_states, keep_area=True)

    frames = []
    for i, state in enumerate(states or config.STATES, 1):
        roads = load_state_roads(state)
        # Restrict polygons to the state's bounding box first; overlay against
        # the full national layer would be needlessly expensive.
        bbox = roads.total_bounds
        cand = polygons.to_crs(EQUAL_AREA_CRS).cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        if not len(cand):
            continue
        frames.append(road_km_by_unit(roads, cand, key))
        if verbose:
            print(f"  {state}: {len(roads):,} road features, "
                  f"{len(frames[-1]):,} {level}s with arterials")

    if not frames:
        raise RuntimeError("no road data assembled")

    # A unit near a state line can appear from two states' road files; sum.
    roads_by_unit = (pd.concat(frames, ignore_index=True)
                     .groupby(key, as_index=False)
                     [["road_km_primary", "road_km_secondary"]].sum())

    out = polygons[[key, "land_area_sqkm"]].merge(roads_by_unit, on=key, how="left")
    for c in ("road_km_primary", "road_km_secondary"):
        out[c] = out[c].fillna(0.0)          # no highway is zero, not missing
    out["road_km_arterial"] = out["road_km_primary"] + out["road_km_secondary"]
    area = out["land_area_sqkm"].replace(0, pd.NA)
    out["road_density_km_sqkm"] = out["road_km_arterial"] / area
    out["has_arterial"] = out["road_km_arterial"] > 0

    dest = config.INTERIM / f"roads_{level}.parquet"
    out.drop(columns=["land_area_sqkm"]).to_parquet(dest, index=False)
    if verbose:
        print(f"  {level}: {len(out):,} units, "
              f"{100*out['has_arterial'].mean():.1f}% with an arterial road "
              f"-> {dest}")
    return out
