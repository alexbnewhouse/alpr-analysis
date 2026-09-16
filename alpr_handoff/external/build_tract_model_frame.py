"""Turn the camera-level covariates CSV into a model-ready tract frame.

The source CSV is one row per camera, and only contains tracts that have at
least one camera. Modelling it directly conditions on the outcome. This script:

  1. reads GEOIDs as strings (they are floats in the source -- California
     tracts lose their leading zero and mis-join silently);
  2. aggregates cameras to tract level;
  3. expands to the FULL tract universe from TIGER, filling zeros;
  4. attaches county and state keys so fixed effects are available.

    python external/build_tract_model_frame.py
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from flock_alpr import config, geocode  # noqa: E402

SOURCE = HERE.parent / "cameras_with_covariates_tract.csv"
OUT = HERE / "data"

RETAIL = (r"lowe'?s|home ?depot|walmart|target|simon property|meijer|kroger|"
          r"costco|menards|best buy|sam'?s club|mall|shopping|kohl|walgreens|"
          r"cvs|dollar (?:general|tree)|autozone|ikea")
POLICE = (r"police|sheriff|constable|marshal|state patrol|highway patrol|"
          r"public safety|department of correct")


def geoid(series: pd.Series, width: int) -> pd.Series:
    """Recover a zero-padded string GEOID from a float column."""
    return (
        pd.to_numeric(series, errors="coerce")
        .astype("Int64")
        .astype(str)
        .replace("<NA>", pd.NA)
        .str.zfill(width)
    )


def load_cameras() -> pd.DataFrame:
    df = pd.read_csv(SOURCE, low_memory=False)
    df["tract_geoid"] = geoid(df["geoid_tract"], 11)
    df["county_fips"] = geoid(df["geoid_county"], 5)
    df = df[df["tract_geoid"].notna()].copy()

    op = df["operator_raw"].fillna("")
    df["is_retail"] = op.str.contains(RETAIL, case=False, regex=True)
    df["is_police"] = op.str.contains(POLICE, case=False, regex=True)
    df["is_flock"] = df["is_flock"].fillna(0).astype(bool)
    return df


def tract_universe() -> pd.DataFrame:
    """Every US tract from TIGER -- the denominator the CSV is missing."""
    shp = geocode.load_shapes("tract", states=config.STATES)
    out = pd.DataFrame({"tract_geoid": shp["tract_geoid"].astype(str)})
    out["county_fips"] = out["tract_geoid"].str[:5]
    out["state_fips"] = out["tract_geoid"].str[:2]
    return out.drop_duplicates("tract_geoid")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cams = load_cameras()
    print(f"  cameras: {len(cams):,} in {cams['tract_geoid'].nunique():,} tracts")

    agg = cams.groupby("tract_geoid").agg(
        n_cameras=("osm_id", "count"),
        n_flock=("is_flock", "sum"),
        n_retail=("is_retail", "sum"),
        n_police=("is_police", "sum"),
        first_seen=("osm_timestamp", "min"),
    ).reset_index()

    universe = tract_universe()
    print(f"  TIGER tract universe: {len(universe):,}")

    # Covariates come from ONE source for every tract. The supplied CSV only
    # carries them for camera-bearing tracts, so using it for those and ACS for
    # the zeros would put a source discontinuity exactly where the treatment
    # variation is. Pull ACS for all tracts instead.
    acs_path = config.INTERIM / "acs_tract.parquet"
    if not acs_path.exists():
        raise SystemExit(
            "missing acs_tract.parquet -- run:\n"
            "  export CENSUS_API_KEY=...\n"
            "  .venv/bin/python -c 'from flock_alpr import covariates;"
            " covariates.fetch_acs(\"tract\")'"
        )
    acs = pd.read_parquet(acs_path)
    acs["tract_geoid"] = acs["tract_geoid"].astype(str).str.zfill(11)
    acs = acs.drop(columns=[c for c in ("NAME",) if c in acs.columns])
    print(f"  ACS tracts: {len(acs):,}")

    frame = (universe
             .merge(agg, on="tract_geoid", how="left")
             .merge(acs, on="tract_geoid", how="left"))

    for c in ["n_cameras", "n_flock", "n_retail", "n_police"]:
        frame[c] = frame[c].fillna(0).astype(int)

    frame["has_camera"] = frame["n_cameras"] > 0
    frame["has_flock"] = frame["n_flock"] > 0

    matched = frame["population"].notna()
    print(f"  tracts with cameras : {frame['has_camera'].sum():,} "
          f"({100 * frame['has_camera'].mean():.1f}%)")
    print(f"  tracts with zeros   : {(~frame['has_camera']).sum():,}")
    print(f"  tracts w/ covariates: {matched.sum():,} "
          f"({100 * matched.mean():.1f}%)")
    print(f"  MISSING covariates  : {(~matched).sum():,} "
          f"-- these are almost all zero-camera tracts")

    frame.to_parquet(OUT / "tract_model_frame.parquet", index=False)
    frame.to_csv(OUT / "tract_model_frame.csv", index=False)
    print(f"\nwrote {len(frame):,} tracts -> {OUT / 'tract_model_frame.parquet'}")

    mean, var = frame["n_cameras"].mean(), frame["n_cameras"].var()
    print(f"\n  full-universe counts: mean={mean:.3f} var={var:.3f} "
          f"ratio={var / mean:.1f}  zeros={100 * (frame['n_cameras'] == 0).mean():.1f}%")


if __name__ == "__main__":
    main()
