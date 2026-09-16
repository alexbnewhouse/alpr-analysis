"""Camera-level analytical dataset: one row per camera, covariates at every scale.

Each camera carries its own attributes, its geography keys, and the full ACS
covariate set for the tract, place, county and ZCTA that contain it, plus
jurisdiction crime. Contextual columns are suffixed with their level, so
`median_hh_income_tract` and `median_hh_income_county` sit side by side.

    python external/build_camera_dataset.py

NOTE ON USE: this file has no rows for places without cameras, so it cannot
answer "what predicts a place having any cameras". Use the model_frame_*
files for that. This one answers "what kind of place is a camera in".
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from flock_alpr import config  # noqa: E402
from build_multilevel_panels import (  # noqa: E402
    crime_by_jurisdiction, place_to_county, zcta_to_county,
)

OUT = HERE / "data"
CAMERAS = OUT / "cameras_geocoded.parquet"

# level -> (camera key column, ACS file, geoid width)
LEVELS = {
    "tract": ("tract_geoid", "acs_tract.parquet", 11),
    "place": ("place_geoid", "acs_place.parquet", 7),
    "county": ("county_fips", "acs_county.parquet", 5),
    "zcta": ("zcta", "acs_zcta.parquet", 5),
}

# Kept out of the per-level suffixing: identifiers, not covariates.
DROP_FROM_ACS = {"NAME", "acs_year"}


def load_cameras() -> pd.DataFrame:
    cams = pd.read_parquet(CAMERAS)
    for key, width in [("tract_geoid", 11), ("place_geoid", 7),
                       ("county_fips", 5), ("zcta", 5)]:
        if key in cams.columns:
            cams[key] = cams[key].astype("string").str.zfill(width)
    return cams


def attach_level(cams: pd.DataFrame, level: str) -> pd.DataFrame:
    """Left-join one geography's context block, suffixing every column.

    Covers ACS plus the separately-built road exposure and land-use measures,
    so a camera carries all three at every scale that contains it.
    """
    key, acs_file, width = LEVELS[level]
    blocks = [pd.read_parquet(config.INTERIM / acs_file)]
    for extra in ("roads", "landuse"):
        path = config.INTERIM / f"{extra}_{level}.parquet"
        if path.exists():
            blocks.append(pd.read_parquet(path))

    out = cams
    for blk in blocks:
        blk = blk.copy()
        blk[key] = blk[key].astype("string").str.zfill(width)
        blk = blk.drop(columns=[c for c in DROP_FROM_ACS if c in blk.columns])
        blk = blk.drop_duplicates(key)
        blk = blk.rename(columns={c: f"{c}_{level}" for c in blk.columns if c != key})
        out = out.merge(blk, on=key, how="left")
    return out


def attach_camera_density(cams: pd.DataFrame) -> pd.DataFrame:
    """How many cameras share each unit -- the local density around this one."""
    out = cams
    for level, (key, _, _) in LEVELS.items():
        counts = (cams.dropna(subset=[key])
                  .groupby(key)
                  .agg(**{f"n_cameras_{level}": ("osm_id", "count"),
                          f"n_flock_{level}": ("is_flock", "sum")})
                  .reset_index())
        out = out.merge(counts, on=key, how="left")
        for c in (f"n_cameras_{level}", f"n_flock_{level}"):
            out[c] = out[c].fillna(0).astype(int)
    return out


def attach_crime(cams: pd.DataFrame) -> pd.DataFrame:
    county_crime, place_crime = crime_by_jurisdiction()
    out = cams
    if county_crime is not None:
        county_crime["county_fips"] = (county_crime["county_fips"]
                                       .astype("string").str.zfill(5))
        out = out.merge(county_crime, on="county_fips", how="left")
    if place_crime is not None:
        place_crime["place_geoid"] = (place_crime["place_geoid"]
                                      .astype("string").str.zfill(7))
        out = out.merge(place_crime, on="place_geoid", how="left")
    return out


def add_per_capita(df: pd.DataFrame) -> pd.DataFrame:
    """Crime rates per 100k, using the population of the matching geography."""
    out = df
    for src_pop, prefix in [("population_county", "county"),
                            ("population_place", "place")]:
        if src_pop not in out.columns:
            continue
        pop = out[src_pop].replace(0, pd.NA)
        for kind in ("violent", "property"):
            col = f"{kind}_crime_{prefix}"
            if col in out.columns:
                out[f"{kind}_rate_{prefix}"] = 1e5 * out[col] / pop
    return out


def main():
    cams = load_cameras()
    print(f"  cameras: {len(cams):,}")

    df = attach_camera_density(cams)
    for level in LEVELS:
        df = attach_level(df, level)
        print(f"  + {level} covariates -> {len(df.columns)} cols")

    df = add_per_capita(attach_crime(df))

    # Ordering: identity, geography keys, camera attributes, then context.
    keys = ["osm_id", "lat", "lon", "state", "tract_geoid", "place_geoid",
            "county_fips", "zcta"]
    front = [c for c in keys if c in df.columns]
    rest = [c for c in df.columns if c not in front]
    df = df[front + rest]

    df.to_parquet(OUT / "camera_dataset.parquet", index=False)
    df.to_csv(OUT / "camera_dataset.csv", index=False)

    print(f"\nwrote {len(df):,} cameras x {len(df.columns)} columns")
    print(f"  -> {OUT / 'camera_dataset.parquet'}")
    print(f"  -> {OUT / 'camera_dataset.csv'}")

    print("\ncoverage of key contextual columns:")
    for c in ["median_hh_income_tract", "median_hh_income_place",
              "median_hh_income_county", "median_hh_income_zcta",
              "violent_crime_county", "violent_crime_place"]:
        if c in df.columns:
            print(f"  {c:28} {100 * df[c].notna().mean():5.1f}%")


if __name__ == "__main__":
    main()
