"""Stage 4 - assign each camera point to a ZCTA, Census place, and county.

Note on ZIP: USPS ZIP codes are delivery routes, not areas. This uses Census
ZCTAs, which approximate them. Cameras frequently sit on roads that form ZCTA
boundaries, so a small share of assignments are arbitrary at the margin.
"""
import zipfile

import geopandas as gpd
import pandas as pd

from . import config, http

TIGER = "https://www2.census.gov/geo/tiger/TIGER2024"

# level -> (source key column, output column)
KEYS = {
    "zcta": ("ZCTA5CE20", "zcta"),
    "place": ("GEOID", "place_geoid"),
    "county": ("GEOID", "county_fips"),
    "tract": ("GEOID", "tract_geoid"),
}

# Levels published by TIGER as one file per state rather than nationally.
PER_STATE = {
    "place": "PLACE/tl_2024_{fips}_place.zip",
    "tract": "TRACT/tl_2024_{fips}_tract.zip",
}

NATIONAL_URLS = {
    "zcta": f"{TIGER}/ZCTA520/tl_2024_us_zcta520.zip",
    "county": f"{TIGER}/COUNTY/tl_2024_us_county.zip",
}


def _cached_shapefile(url: str, name: str):
    """Download a TIGER zip once and return the local path."""
    dest = config.TIGER_DIR / name
    if not dest.exists():
        dest.write_bytes(http.fetch(url, timeout=900))
    if not zipfile.is_zipfile(dest):
        dest.unlink()
        raise RuntimeError(f"{url} did not return a zip archive")
    return dest


def load_shapes(level: str, states=None, keep_area=False) -> gpd.GeoDataFrame:
    """Load TIGER polygons for one level.

    keep_area adds ``land_area_sqkm`` from the ALAND attribute (square metres
    of land, excluding water).
    """
    src_col, out_col = KEYS[level]

    # 2020-vintage ZCTA files suffix their attributes: ALAND20, not ALAND.
    area_col = "ALAND20" if level == "zcta" else "ALAND"
    cols = [src_col, "geometry"] + ([area_col] if keep_area else [])

    if level in NATIONAL_URLS:
        path = _cached_shapefile(NATIONAL_URLS[level], f"{level}.zip")
        gdf = gpd.read_file(f"zip://{path}", columns=cols)
    else:
        # Places and tracts are published per state only.
        template = PER_STATE[level]
        frames = []
        for st in (states or config.STATES):
            fips = config.STATE_FIPS[st]
            url = f"{TIGER}/{template.format(fips=fips)}"
            path = _cached_shapefile(url, f"{level}_{fips}.zip")
            frames.append(gpd.read_file(f"zip://{path}", columns=cols))
        gdf = pd.concat(frames, ignore_index=True)
        gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=frames[0].crs)

    gdf = gdf.rename(columns={src_col: out_col})
    keep = [out_col, "geometry"]
    if keep_area and area_col in gdf.columns:
        gdf["land_area_sqkm"] = pd.to_numeric(gdf[area_col], errors="coerce") / 1e6
        keep.append("land_area_sqkm")
    return gdf[keep].to_crs("EPSG:4326")


# Longest first: " CITY AND BOROUGH" must be tested before " BOROUGH", or
# "Juneau City and Borough" normalises to "JUNEAU CITY AND".
#
# " CITY" is deliberately NOT stripped. Virginia's independent cities collide
# with same-named counties -- Richmond city and Richmond County are different
# jurisdictions with different FIPS codes. Keeping the word distinguishes them,
# and both sources spell it the same way.
COUNTY_SUFFIXES = tuple(sorted(
    (" CITY AND BOROUGH", " CENSUS AREA", " MUNICIPALITY", " BOROUGH",
     " PARISH", " COUNTY"),
    key=len, reverse=True,
))


def normalize_county(name: str) -> str:
    """Normalise a county name for joining across sources.

    The Atlas of Surveillance writes "Polk County"; TIGER writes "Polk". Also
    handles Louisiana parishes and the Alaska borough variants.
    """
    n = (name or "").strip().upper()
    for suffix in COUNTY_SUFFIXES:
        if n.endswith(suffix):
            return n[: -len(suffix)].strip()
    return n


def county_crosswalk() -> pd.DataFrame:
    """county_fips <-> (state, normalized county name), from TIGER."""
    path = _cached_shapefile(NATIONAL_URLS["county"], "county.zip")
    gdf = gpd.read_file(
        f"zip://{path}", columns=["GEOID", "NAME", "STATEFP", "geometry"]
    )
    fips_to_state = {v: k for k, v in config.STATE_FIPS.items()}
    out = pd.DataFrame({
        "county_fips": gdf["GEOID"],
        "state": gdf["STATEFP"].map(fips_to_state),
        "county_norm": gdf["NAME"].map(normalize_county),
    })
    return out.dropna(subset=["state"]).drop_duplicates()


def join_geographies(cameras: pd.DataFrame, shapes: dict) -> gpd.GeoDataFrame:
    """Append zcta / place_geoid / county_fips to each camera point.

    Points falling outside every polygon keep the row with a null key; only
    rows lacking coordinates entirely are dropped.
    """
    cams = cameras.dropna(subset=["lat", "lon"]).copy()
    dropped = len(cameras) - len(cams)
    if dropped:
        print(f"  dropped {dropped} rows lacking coordinates")

    pts = gpd.GeoDataFrame(
        cams,
        geometry=gpd.points_from_xy(cams["lon"], cams["lat"]),
        crs="EPSG:4326",
    ).reset_index(drop=True)

    for level, shp in shapes.items():
        col = KEYS[level][1]
        joined = gpd.sjoin(
            pts[["geometry"]], shp[[col, "geometry"]], how="left", predicate="within"
        )
        joined = joined[~joined.index.duplicated(keep="first")]
        pts[col] = joined[col].values

    return pts


def run(force=False) -> gpd.GeoDataFrame:
    cams = pd.read_parquet(config.RAW / "osm_alpr_nodes.parquet")
    states = sorted(cams["state"].dropna().unique())
    shapes = {
        "zcta": load_shapes("zcta"),
        "county": load_shapes("county"),
        "place": load_shapes("place", states=states),
        "tract": load_shapes("tract", states=states),
    }
    out = join_geographies(cams, shapes)

    for col in ("zcta", "tract_geoid", "place_geoid", "county_fips"):
        pct = 100 * out[col].notna().mean()
        print(f"  {col}: {pct:.1f}% assigned")

    out.drop(columns="geometry").to_parquet(
        config.INTERIM / "cameras_geocoded.parquet", index=False
    )
    print(f"wrote {len(out)} -> {config.INTERIM / 'cameras_geocoded.parquet'}")
    return out
