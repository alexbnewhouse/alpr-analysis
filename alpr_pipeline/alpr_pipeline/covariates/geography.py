"""Assign census GEOIDs to camera coordinates by offline point-in-polygon.

Uses Census cartographic boundary files (public domain, generalized to 1:500k),
downloaded once and cached. Everything runs locally: geocoding 125k points
through the Census Geocoder API would take tens of thousands of calls, and its
coordinate endpoint has no batch mode.

The 500k generalization is appropriate here -- it simplifies coastlines, not
interior tract boundaries, so an inland camera lands in the same tract it would
under the full-resolution TIGER file. Coastal points are handled by the same
nearest-polygon fallback used for state assignment.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from .variables import SUMMARY_LEVELS

log = logging.getLogger(__name__)

CB_YEAR = 2023
CB_URL = (
    "https://www2.census.gov/geo/tiger/GENZ{year}/shp/"
    "cb_{year}_us_{slug}_500k.zip"
)
USER_AGENT = "alpr-research-pipeline/1.0 (academic research)"

# Cameras on bridges and barrier islands fall outside land polygons. 2 km is
# far tighter than the state-level fallback: tracts are small, and snapping a
# point 16 km to a neighbouring tract would be an error rather than a recovery.
NEAREST_TOLERANCE_M = 2_000

# The nearest-neighbour search needs a projected CRS -- distances in degrees
# are not a length. Web Mercator is used because it is valid for all US
# territories including Alaska and Puerto Rico, unlike a CONUS-specific Albers.
# It inflates distance by 1/cos(latitude), so the effective real-world
# tolerance is *tighter* than 2 km (~1.5 km at 40 deg, ~700 m in northern
# Alaska). Erring conservative is the right direction here.
NEAREST_CRS = "EPSG:3857"


def _download_boundary(slug: str, cache_dir: Path, year: int = CB_YEAR) -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"cb_{year}_us_{slug}_500k.zip"
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    url = CB_URL.format(year=year, slug=slug)
    log.info("Downloading boundaries: %s", url)
    with requests.get(url, stream=True, timeout=900,
                      headers={"User-Agent": USER_AGENT}) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    log.info("Cached %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


def load_boundaries(level: str, cache_dir: Path,
                    year: int = CB_YEAR) -> gpd.GeoDataFrame:
    sl = SUMMARY_LEVELS[level]
    path = _download_boundary(sl.boundary_slug, cache_dir, year)
    gdf = gpd.read_file(f"zip://{path}", columns=["GEOID", "geometry"])
    gdf = gdf.rename(columns={"GEOID": "geoid"})[["geoid", "geometry"]]
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    else:
        gdf = gdf.to_crs("EPSG:4326")
    log.info("Loaded %d %s polygons", len(gdf), level)
    return gdf


def assign_geoids(cameras: pd.DataFrame, level: str, cache_dir: Path,
                  year: int = CB_YEAR,
                  tolerance_m: float = NEAREST_TOLERANCE_M) -> pd.Series:
    """Return a Series of GEOIDs aligned to `cameras`, indexed like it.

    `cameras` needs `lat` and `lon` columns. Points outside every polygon fall
    back to the nearest polygon within `tolerance_m` metres; beyond that they
    stay NULL rather than being snapped somewhere arbitrary.
    """
    polys = load_boundaries(level, cache_dir, year)

    points = gpd.GeoDataFrame(
        cameras[["lat", "lon"]].copy(),
        geometry=gpd.points_from_xy(cameras["lon"], cameras["lat"]),
        crs="EPSG:4326",
    )

    log.info("Spatial join: %d points into %d %s polygons",
             len(points), len(polys), level)
    joined = gpd.sjoin(points, polys, how="left", predicate="within")
    # A point on a shared boundary matches both neighbours; keep the first so
    # the result stays one row per camera.
    joined = joined[~joined.index.duplicated(keep="first")]
    result = joined["geoid"].reindex(cameras.index)

    missing = result.isna()
    n_missing = int(missing.sum())
    if n_missing and tolerance_m > 0:
        log.info("%d points outside all polygons; trying nearest within %.0f m",
                 n_missing, tolerance_m)
        # Reproject both sides: max_distance is in CRS units, and degrees are
        # not a length.
        stray = points.loc[missing.values].to_crs(NEAREST_CRS)
        near = gpd.sjoin_nearest(
            stray, polys.to_crs(NEAREST_CRS), how="left",
            max_distance=tolerance_m, distance_col="_dist",
        )
        near = near[~near.index.duplicated(keep="first")]
        result.loc[missing.values] = near["geoid"].reindex(stray.index).values

    still = int(result.isna().sum())
    log.info("Assigned %s for %d/%d cameras (%d unassigned)",
             level, len(result) - still, len(result), still)
    return result
