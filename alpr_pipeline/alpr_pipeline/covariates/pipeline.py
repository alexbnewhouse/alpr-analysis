"""Wire camera locations to census geography and ACS covariates.

Produces three artefacts per summary level, because they answer different
questions:

* ``cameras_with_covariates`` -- one row per camera, with its geography's
  covariates attached. For camera-level descriptive work.
* ``acs_<level>``             -- one row per geography nationwide. The
  reference table.
* ``<level>_panel``           -- one row per geography with camera counts
  joined onto the covariates. **This is the unit of analysis for "what
  predicts where surveillance gets deployed"**: it includes the geographies
  with zero cameras, without which any model is fit on a truncated sample.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .acs import build_covariates
from .geography import assign_geoids
from .variables import MEASURES, SUMMARY_LEVELS

log = logging.getLogger(__name__)


def attach_geography(cameras: pd.DataFrame, levels: list[str],
                     cache_dir: Path) -> pd.DataFrame:
    """Add a geoid_<level> column to `cameras` for each requested level."""
    out = cameras.copy()
    for level in levels:
        col = SUMMARY_LEVELS[level].geoid_column
        out[col] = assign_geoids(out, level, cache_dir)
    return out


def build_panel(cameras: pd.DataFrame, covariates: pd.DataFrame,
                level: str) -> pd.DataFrame:
    """One row per geography: camera counts + ACS covariates.

    Left-joined onto the *covariate* frame, not the camera frame, so every
    geography in the country appears -- including the ~80% with no cameras.
    Those are the control observations; dropping them would bias any model of
    deployment toward places that already have cameras.
    """
    col = SUMMARY_LEVELS[level].geoid_column
    has_geo = cameras[cameras[col].notna()]

    agg: dict[str, tuple] = {
        "camera_count": ("osm_id", "size"),
        "flock_count": ("is_flock", lambda s: int((s == 1).sum())),
    }
    # Mapping-effort controls, available only from an Overpass harvest. The
    # outcome here is "cameras *mapped* in this tract", not "cameras present",
    # so any model needs some handle on volunteer attention. Distinct mappers
    # and the first/last edit dates are the best proxies this data affords.
    if "osm_user" in has_geo.columns and has_geo["osm_user"].notna().any():
        agg["n_mappers"] = ("osm_user", "nunique")
    if "osm_timestamp" in has_geo.columns and has_geo["osm_timestamp"].notna().any():
        agg["first_mapped"] = ("osm_timestamp", "min")
        agg["last_mapped"] = ("osm_timestamp", "max")

    counts = (
        has_geo.groupby(col)
        .agg(**agg)
        .reset_index()
        .rename(columns={col: "geoid"})
    )

    panel = covariates.merge(counts, on="geoid", how="left")
    for c in ("camera_count", "flock_count", "n_mappers"):
        if c in panel.columns:
            panel[c] = panel[c].fillna(0).astype("int64")
    panel["has_camera"] = (panel["camera_count"] > 0).astype("int64")

    # Per-capita exposure, the usual outcome for a deployment model. Guarded
    # against the many zero-population tracts (parks, industrial, water).
    pop = panel.get("pop_total")
    if pop is not None:
        panel["cameras_per_10k"] = (
            panel["camera_count"].div(pop.where(pop > 0)) * 10_000
        )

    log.info(
        "%s panel: %d geographies, %d with >=1 camera (%.1f%%), %d cameras placed",
        level, len(panel), int(panel["has_camera"].sum()),
        100 * panel["has_camera"].mean(), int(panel["camera_count"].sum()),
    )
    return panel


def attach_county_level(frame: pd.DataFrame, county: pd.DataFrame,
                        level: str, prefix: str = "") -> pd.DataFrame:
    """Broadcast county-level covariates onto a finer-grained frame.

    A tract GEOID embeds its county: the first 5 characters are state+county
    FIPS. So county measures (crime, ideology, election returns) attach to
    tracts and block groups without any spatial work. Every tract in a county
    receives the same value -- that is a real limitation to acknowledge when
    modelling, not a defect of the join.
    """
    if level == "county":
        key = frame["geoid"]
    elif level in ("tract", "bg"):
        key = frame["geoid"].str[:5]
    else:  # place GEOIDs do not embed a county
        log.warning("Cannot attach county data to %s level; skipping", level)
        return frame

    right = county.copy()
    if prefix:
        right = right.rename(columns={
            c: f"{prefix}{c}" for c in right.columns if c != "geoid"
        })

    out = frame.copy()
    out["_county_key"] = key
    out = out.merge(right.rename(columns={"geoid": "_county_key"}),
                    on="_county_key", how="left")
    return out.drop(columns=["_county_key"])


def run(cameras: pd.DataFrame, level: str, cache_dir: Path,
        extra_levels: list[str] | None = None,
        year: int = 2023, force: bool = False,
        political: bool = False, crime: bool = False,
        crime_identity=None, crime_year: int = 2023,
        ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Full covariate build. Returns (cameras_joined, covariates, panel)."""
    levels = [level] + [ln for ln in (extra_levels or []) if ln != level]

    cameras_geo = attach_geography(cameras, levels, cache_dir)
    covariates = build_covariates(level, cache_dir, MEASURES, year, force)

    if political:
        covariates = _add_political(covariates, level, cache_dir)
    if crime:
        covariates = _add_crime(covariates, level, cache_dir,
                                crime_identity, crime_year)

    col = SUMMARY_LEVELS[level].geoid_column
    cameras_joined = cameras_geo.merge(
        covariates.rename(columns={"geoid": col}), on=col, how="left"
    )

    panel = build_panel(cameras_geo, covariates, level)
    return cameras_joined, covariates, panel


def _add_political(covariates: pd.DataFrame, level: str,
                   cache_dir: Path) -> pd.DataFrame:
    """Attach VEST reallocated returns and AIP ideology."""
    from .political import fetch_aip, fetch_vest_reallocated

    out = covariates
    if level in ("tract", "bg"):
        # 2020 only, deliberately. VEST's 2016 file is built on 2010-vintage
        # census geography: 15.6% of its tract GEOIDs do not exist in the 2020
        # vintage, and it matches only 70.7% of 2023 ACS tracts. Joining it to
        # 2020-vintage GEOIDs would attach returns to the wrong ground for the
        # redefined tracts, and a 2016->2020 "swing" computed across the two
        # vintages would be an artefact of boundary changes rather than a real
        # political shift. Use `fetch_vest_reallocated(..., year=2016)`
        # directly if you need it and can handle the crosswalk yourself.
        vest = fetch_vest_reallocated(cache_dir, level, 2020)
        out = out.merge(vest, on="geoid", how="left")
    else:
        log.info("VEST reallocation is tract/bg only; skipping at %s", level)

    # Ideology is published at county and place, so it broadcasts down.
    if level == "place":
        out = out.merge(fetch_aip(cache_dir, "place"), on="geoid", how="left")
    else:
        out = attach_county_level(out, fetch_aip(cache_dir, "county"), level)

    return out


def _add_crime(covariates: pd.DataFrame, level: str, cache_dir: Path,
               identity, year: int) -> pd.DataFrame:
    """Attach UCR crime rates. Agency-level data rolled up to county/place."""
    from .crime import agency_year, crime_by_county, crime_by_place, fetch_ucr_year

    ucr = agency_year(fetch_ucr_year(year, cache_dir, identity))

    if level == "place":
        return covariates.merge(crime_by_place(ucr), on="geoid", how="left")
    return attach_county_level(covariates, crime_by_county(ucr), level)
