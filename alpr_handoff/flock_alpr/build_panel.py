"""Stage 6 - assemble the two analysis-ready tables.

panel_geo      geography x covariates, with camera counts (cross-section)
panel_agency   ORI x adoption/observation dates, crime, and jurisdiction ACS

Also computes the discovery-lag calibration: the gap between when OSM first saw
a camera in an agency's county and when the Atlas of Surveillance first cited
that agency. Two independent observation processes; the distribution of the gap
estimates how much of the apparent timing is observation rather than adoption.
"""
import pandas as pd

from . import config

GEO_KEYS = {
    "zcta": "zcta",
    "tract": "tract_geoid",
    "place": "place_geoid",
    "county": "county_fips",
}

# Tract is the primary analysis unit: unlike ZCTA it nests cleanly inside
# counties, so county fixed effects are available. ZCTA is retained for
# descriptive/communication purposes; county for the multi-scale MAUP check.
LEVELS = ("tract", "zcta", "place", "county")


def aggregate_cameras(geocoded: pd.DataFrame, level: str) -> pd.DataFrame:
    """Camera and Flock counts per geography.

    Flock status comes from the coalesced ``vendor`` column, not ``manufacturer``
    alone -- see extract_osm.VENDOR_KEYS for why that distinction matters.
    """
    from .extract_osm import is_flock

    key = GEO_KEYS[level]
    df = geocoded.dropna(subset=[key]).copy()
    vendor = df["vendor"] if "vendor" in df.columns else df.get("manufacturer")
    df["_flock"] = is_flock(vendor)
    return (
        df.groupby(key)
        .agg(
            camera_count=("osm_id", "count"),
            flock_count=("_flock", "sum"),
            first_seen=("osm_timestamp", "min"),
            last_seen=("osm_timestamp", "max"),
        )
        .reset_index()
    )


def osm_first_seen_by_county(geocoded: pd.DataFrame) -> pd.DataFrame:
    return (
        geocoded.dropna(subset=["county_fips"])
        .groupby("county_fips")["osm_timestamp"]
        .min()
        .reset_index()
        .rename(columns={"osm_timestamp": "osm_first_seen"})
    )


def attach_county_fips(aos: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Give Atlas agency rows a county FIPS so they can meet the OSM data.

    The Atlas records a county *name*; OSM cameras carry a FIPS code from the
    spatial join. This is the bridge between them.
    """
    from .geocode import normalize_county

    out = aos.copy()
    out["county_norm"] = out["county"].map(normalize_county)
    return out.merge(crosswalk, on=["state", "county_norm"], how="left")


def osm_first_seen_by_agency(aos_with_fips: pd.DataFrame,
                             osm_by_county: pd.DataFrame) -> pd.DataFrame:
    """Carry the OSM first-seen date from county level down to agency (ORI).

    County is the finest geography the two sources share: the Atlas names a
    county, OSM cameras carry a FIPS from the spatial join. For agencies whose
    jurisdiction is smaller than a county this is an upper bound on how early
    OSM could have seen that agency's cameras.
    """
    bridge = aos_with_fips.loc[
        aos_with_fips["ori9"].notna() & aos_with_fips["county_fips"].notna(),
        ["ori9", "county_fips"],
    ].drop_duplicates()
    return (
        bridge.merge(osm_by_county, on="county_fips", how="inner")
        .groupby("ori9", as_index=False)["osm_first_seen"].min()
    )


def discovery_lag(osm_first_seen: pd.DataFrame, aos: pd.DataFrame) -> pd.DataFrame:
    """Gap in days between the two independent observation dates.

    Positive lag: OSM volunteers saw the camera after the Atlas cited the agency.
    """
    merged = osm_first_seen.merge(
        aos[["ori9", "earliest_source_date"]].rename(
            columns={"earliest_source_date": "aos_first_seen"}
        ),
        on="ori9",
        how="inner",
    )
    merged["lag_days"] = (
        merged["osm_first_seen"] - merged["aos_first_seen"]
    ).dt.days
    return merged


def build_geo_panel(geocoded: pd.DataFrame, acs: pd.DataFrame,
                    level: str) -> pd.DataFrame:
    key = GEO_KEYS[level]
    counts = aggregate_cameras(geocoded, level)
    if acs is None or not len(acs):
        return counts
    panel = counts.merge(acs, on=key, how="left")
    if "population" in panel.columns:
        pop = panel["population"].replace(0, pd.NA)
        panel["cameras_per_10k"] = 10_000 * panel["camera_count"] / pop
        panel["flock_per_10k"] = 10_000 * panel["flock_count"] / pop
    return panel


def build_agency_panel(aos: pd.DataFrame, crime: pd.DataFrame = None,
                       lag: pd.DataFrame = None) -> pd.DataFrame:
    panel = aos[aos["ori9"].notna()].copy()
    panel = panel.drop_duplicates(subset=["ori9", "vendor"])
    if lag is not None and len(lag):
        panel = panel.merge(
            lag[["ori9", "osm_first_seen", "lag_days"]], on="ori9", how="left"
        )
    if crime is not None and len(crime):
        panel = panel.merge(crime, on="ori9", how="left")
    return panel


def run():
    geocoded = pd.read_parquet(config.INTERIM / "cameras_geocoded.parquet")
    aos = pd.read_parquet(config.RAW / "aos_alpr_agencies.parquet")

    for level in LEVELS:
        acs_path = config.INTERIM / f"acs_{level}.parquet"
        acs = pd.read_parquet(acs_path) if acs_path.exists() else None
        if acs is None:
            print(f"  {level}: no ACS file, writing counts only")
        panel = build_geo_panel(geocoded, acs, level)
        panel.to_parquet(config.DATA / f"panel_geo_{level}.parquet", index=False)
        print(f"  panel_geo_{level}: {len(panel)} rows")

    crime_path = config.INTERIM / "crime_by_ori.parquet"
    crime = pd.read_parquet(crime_path) if crime_path.exists() else None

    # Discovery-lag calibration: bridge Atlas county names to OSM county FIPS,
    # then compare the two independent observation dates per agency.
    from . import geocode

    aos_fips = attach_county_fips(aos, geocode.county_crosswalk())
    matched = aos_fips["county_fips"].notna().mean()
    print(f"  county name -> FIPS matched for {100 * matched:.1f}% of Atlas rows")

    osm_by_ori = osm_first_seen_by_agency(
        aos_fips, osm_first_seen_by_county(geocoded)
    )
    lag = discovery_lag(osm_by_ori, aos)
    if len(lag):
        lag.to_parquet(config.DATA / "discovery_lag.parquet", index=False)
        d = lag["lag_days"].describe()
        print(f"  discovery_lag: n={int(d['count'])} "
              f"median={lag['lag_days'].median():.0f}d "
              f"IQR=[{lag['lag_days'].quantile(.25):.0f}, "
              f"{lag['lag_days'].quantile(.75):.0f}]d")

    agency_panel = build_agency_panel(aos, crime, lag)
    agency_panel.to_parquet(config.DATA / "panel_agency.parquet", index=False)
    print(f"  panel_agency: {len(agency_panel)} rows")
    return agency_panel
