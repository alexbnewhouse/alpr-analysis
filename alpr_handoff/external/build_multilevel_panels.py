"""Build model frames at every geography level, with the full zero universe.

Reviewers will ask for multi-scale results (MAUP), so each level gets the same
treatment: complete universe of units, zeros filled, one consistent covariate
source, and crime attached where a jurisdiction mapping exists.

    python external/build_multilevel_panels.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from flock_alpr import config, geocode  # noqa: E402
from build_tract_model_frame import geoid, load_cameras  # noqa: E402

OUT = HERE / "data"

# level -> (key column, universe source, ACS file, geoid width)
LEVELS = {
    "tract": ("tract_geoid", "tract", "acs_tract.parquet", 11),
    "place": ("place_geoid", "place", "acs_place.parquet", 7),
    "county": ("county_fips", "county", "acs_county.parquet", 5),
    "zcta": ("zcta", "zcta", "acs_zcta.parquet", 5),
}


def universe(level: str) -> pd.DataFrame:
    """Every unit at this level, with its land area from TIGER.

    Land area matters because camera counts partly track road network extent:
    a rural county with one camera per 500 km2 is not comparable to a dense
    tract with one per 0.5 km2 without an area denominator.
    """
    key, shape_level, _, width = LEVELS[level]
    states = config.STATES if shape_level in ("place", "tract") else None
    shp = geocode.load_shapes(shape_level, states=states, keep_area=True)
    out = pd.DataFrame({key: shp[key].astype(str).str.zfill(width)})
    if "land_area_sqkm" in shp.columns:
        out["land_area_sqkm"] = shp["land_area_sqkm"].values
    return out.drop_duplicates(key)


def add_densities(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-capita and per-area camera rates, plus population density."""
    out = frame
    if "population" in out.columns:
        pop = out["population"].replace(0, pd.NA)
        out["cameras_per_10k"] = 1e4 * out["n_cameras"] / pop
        out["flock_per_10k"] = 1e4 * out["n_flock"] / pop
    if "land_area_sqkm" in out.columns:
        area = out["land_area_sqkm"].replace(0, pd.NA)
        out["cameras_per_sqkm"] = out["n_cameras"] / area
        if "population" in out.columns:
            out["pop_density_sqkm"] = out["population"] / area
    return out


def agency_crime() -> pd.DataFrame:
    """Mean annual offences per agency, 2019-2023, full-reporting years only."""
    crime_path = config.INTERIM / "crime_by_ori.parquet"
    agency_path = config.INTERIM / "fbi_agencies.parquet"
    if not (crime_path.exists() and agency_path.exists()):
        return None

    crime = pd.read_parquet(crime_path)
    # A partially-reported year makes a low-REPORTING agency look like a
    # low-CRIME agency, so only complete years count.
    crime = crime[(crime["months_reported"] >= 12)
                  & crime["year"].between(2019, 2023)]
    agg = crime.groupby("ori9").agg(
        violent_crime=("actual_violent_crime", "mean"),
        property_crime=("actual_property_crime", "mean"),
        crime_years=("year", "nunique"),
    ).reset_index()

    agencies = pd.read_parquet(agency_path)
    return agencies.merge(agg, on="ori9", how="inner")


def crime_by_jurisdiction():
    """Crime aggregated to the geography each agency actually POLICES.

    Attaching crime to the agency's station coordinates would credit a whole
    city's offences to the single tract containing its police station. Crime
    is a jurisdiction-level quantity, so it is aggregated two ways:

      county : every agency whose station falls in the county
      place  : city agencies whose station falls inside that municipality

    Both are then broadcast to finer units (a tract inherits the crime of the
    county and the place that contain it), which is the correct resolution --
    it does not manufacture within-jurisdiction variation that the source data
    does not have.
    """
    geo = agency_crime()
    if geo is None or not len(geo):
        return None, None

    import geopandas as gpd
    geo = geo.dropna(subset=["latitude", "longitude"])
    pts = gpd.GeoDataFrame(
        geo, geometry=gpd.points_from_xy(geo["longitude"], geo["latitude"]),
        crs="EPSG:4326",
    )

    counties = geocode.load_shapes("county")
    by_county = gpd.sjoin(pts, counties[["county_fips", "geometry"]],
                          how="inner", predicate="within")
    county_crime = (by_county.groupby("county_fips")
                    .agg(violent_crime_county=("violent_crime", "sum"),
                         property_crime_county=("property_crime", "sum"),
                         n_agencies_county=("ori9", "nunique"))
                    .reset_index())

    places = geocode.load_shapes("place", states=config.STATES)
    city = pts[pts["agency_type"] == "City"]
    by_place = gpd.sjoin(city, places[["place_geoid", "geometry"]],
                         how="inner", predicate="within")
    place_crime = (by_place.groupby("place_geoid")
                   .agg(violent_crime_place=("violent_crime", "sum"),
                        property_crime_place=("property_crime", "sum"),
                        n_agencies_place=("ori9", "nunique"))
                   .reset_index())

    return county_crime, place_crime


def tract_to_place(width=7) -> pd.DataFrame:
    """Map each tract to the place containing its centroid, where one exists.

    Tracts do not nest inside places, so this is an assignment by centroid --
    a tract straddling a municipal boundary is credited to one side.
    """
    import geopandas as gpd
    tracts = geocode.load_shapes("tract", states=config.STATES)
    places = geocode.load_shapes("place", states=config.STATES)
    cent = tracts.copy()
    cent["geometry"] = cent.to_crs("EPSG:5070").centroid.to_crs("EPSG:4326")
    joined = gpd.sjoin(cent, places[["place_geoid", "geometry"]],
                       how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    out = pd.DataFrame({
        "tract_geoid": joined["tract_geoid"].astype(str).str.zfill(11),
        "place_geoid": joined["place_geoid"],
    })
    out["place_geoid"] = out["place_geoid"].astype("string").str.zfill(width)
    return out


def place_to_county() -> pd.DataFrame:
    """Assign each place to the county containing its centroid.

    Most places sit in one county; a few straddle lines and are credited to
    one side. Needed because places with no police department of their own are
    policed by the county sheriff, so county crime is the right fallback.
    """
    import geopandas as gpd
    places = geocode.load_shapes("place", states=config.STATES)
    counties = geocode.load_shapes("county")
    cent = places.copy()
    cent["geometry"] = cent.to_crs("EPSG:5070").centroid.to_crs("EPSG:4326")
    joined = gpd.sjoin(cent, counties[["county_fips", "geometry"]],
                       how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    return pd.DataFrame({
        "place_geoid": joined["place_geoid"].astype(str).str.zfill(7),
        "county_fips": joined["county_fips"],
    })


def zcta_to_county() -> pd.DataFrame:
    """Assign each ZCTA to the county containing its centroid.

    ZCTAs nest in nothing, which is exactly why they are a poor analysis unit.
    Centroid assignment is the standard workaround and is approximate.
    """
    import geopandas as gpd
    zctas = geocode.load_shapes("zcta")
    counties = geocode.load_shapes("county")
    cent = zctas.copy()
    cent["geometry"] = cent.to_crs("EPSG:5070").centroid.to_crs("EPSG:4326")
    joined = gpd.sjoin(cent, counties[["county_fips", "geometry"]],
                       how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    return pd.DataFrame({
        "zcta": joined["zcta"].astype(str).str.zfill(5),
        "county_fips": joined["county_fips"],
    })


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cams = load_cameras()
    geocoded_path = OUT / "cameras_geocoded.parquet"
    geo = pd.read_parquet(geocoded_path)

    # Bring the CSV's flags onto the geocoded camera table.
    geo["tract_geoid"] = geo["tract_geoid"].astype(str).str.zfill(11)
    flags = cams[["osm_id", "is_retail", "is_police"]].drop_duplicates("osm_id")
    geo = geo.merge(flags, on="osm_id", how="left")
    for c in ("is_retail", "is_police"):
        geo[c] = geo[c].astype("boolean").fillna(False).astype(bool)
    geo["is_flock"] = geo["is_flock"].astype(bool)

    county_crime, place_crime = crime_by_jurisdiction()
    if county_crime is not None:
        print(f"  crime: {len(county_crime):,} counties, "
              f"{len(place_crime):,} places")
    t2p = tract_to_place()
    print(f"  tract->place: {t2p['place_geoid'].notna().sum():,} of "
          f"{len(t2p):,} tracts fall inside a place")
    # ZCTAs do not nest in counties; assign each to the county holding its
    # centroid so county-level crime can still be attached, accepting that
    # a ZCTA spanning a county line is credited to one side.
    z2c = zcta_to_county()
    p2c = place_to_county()

    for level, (key, _, acs_file, width) in LEVELS.items():
        if key not in geo.columns:
            print(f"  {level}: no key column, skipped")
            continue
        g = geo.dropna(subset=[key]).copy()
        g[key] = g[key].astype(str).str.zfill(width)

        agg = g.groupby(key).agg(
            n_cameras=("osm_id", "count"),
            n_flock=("is_flock", "sum"),
            n_retail=("is_retail", "sum"),
            n_police=("is_police", "sum"),
        ).reset_index()

        acs = pd.read_parquet(config.INTERIM / acs_file)
        acs[key] = acs[key].astype(str).str.zfill(width)
        acs = acs.drop(columns=[c for c in ("NAME",) if c in acs.columns])

        frame = (universe(level)
                 .merge(agg, on=key, how="left")
                 .merge(acs, on=key, how="left"))

        # Geography keys first, so crime can be broadcast down from the
        # jurisdictions that actually report it.
        if level == "tract":
            frame["county_fips"] = frame[key].str[:5]
            frame = frame.merge(t2p, on="tract_geoid", how="left")
        elif level == "place":
            frame["state_fips"] = frame[key].str[:2]
            frame = frame.merge(p2c, on="place_geoid", how="left")
        elif level == "zcta":
            frame = frame.merge(z2c, on="zcta", how="left")

        # Exposure and land use, built separately (flock_alpr/roads.py,
        # flock_alpr/landuse.py) because each needs its own source geometry.
        for extra in ("roads", "landuse"):
            path = config.INTERIM / f"{extra}_{level}.parquet"
            if path.exists():
                ex = pd.read_parquet(path)
                ex[key] = ex[key].astype(str).str.zfill(width)
                frame = frame.merge(ex, on=key, how="left")

        if county_crime is not None and "county_fips" in frame.columns:
            frame = frame.merge(county_crime, on="county_fips", how="left")
        if place_crime is not None and "place_geoid" in frame.columns:
            frame = frame.merge(place_crime, on="place_geoid", how="left")

        for c in ("n_cameras", "n_flock", "n_retail", "n_police"):
            frame[c] = frame[c].fillna(0).astype(int)
        frame["has_camera"] = frame["n_cameras"] > 0
        frame = add_densities(frame)

        frame.to_parquet(OUT / f"model_frame_{level}.parquet", index=False)
        cov = 100 * frame["population"].notna().mean()
        cc = (100 * frame["violent_crime_county"].notna().mean()
              if "violent_crime_county" in frame.columns else 0.0)
        pc = (100 * frame["violent_crime_place"].notna().mean()
              if "violent_crime_place" in frame.columns else 0.0)
        print(f"  {level:7} units={len(frame):6,}  "
              f"cameras={frame['has_camera'].sum():6,} "
              f"({100 * frame['has_camera'].mean():4.1f}%)  "
              f"acs={cov:5.1f}%  crime_county={cc:5.1f}%  crime_place={pc:5.1f}%")


if __name__ == "__main__":
    main()
