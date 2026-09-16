"""Build analysis panels from the supplied alpr_cameras_us.xlsx.

Deliberately separate from the flock_alpr pipeline: this reads a fixed,
externally-supplied snapshot rather than querying OSM live. It reuses only the
geocoding helpers, so the spatial join is identical across both tracks and the
two are directly comparable.

    python external/build_external_panels.py

Outputs land in external/data/, never in the main data/ directory.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from flock_alpr import geocode  # noqa: E402  (needs the path insert above)

SOURCE = HERE / "source" / "alpr_cameras_us.xlsx"
OUT = HERE / "data"

# Territories are present in this file but absent from the TIGER state list and
# from most ACS/UCR products. Kept in the camera table, excluded from panels.
TERRITORIES = {"PR", "VI", "GU", "AS", "MP"}

LEVELS = {
    "tract": "tract_geoid",
    "zcta": "zcta",
    "place": "place_geoid",
    "county": "county_fips",
}


def load() -> pd.DataFrame:
    if not SOURCE.exists():
        raise SystemExit(f"missing {SOURCE}")
    df = pd.read_excel(SOURCE)

    # 18 of the 40 columns are entirely empty in this snapshot. Drop them rather
    # than carry dead weight into every downstream join.
    empty = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty)
    print(f"  loaded {len(df):,} rows; dropped {len(empty)} all-null columns")

    df["osm_timestamp"] = pd.to_datetime(df["osm_timestamp"], errors="coerce", utc=True)
    df["is_flock"] = df["is_flock"].astype(bool)
    return df


def aggregate(cams: pd.DataFrame, level: str) -> pd.DataFrame:
    key = LEVELS[level]
    df = cams.dropna(subset=[key])
    return (
        df.groupby(key)
        .agg(
            camera_count=("osm_id", "count"),
            flock_count=("is_flock", "sum"),
            first_seen=("osm_timestamp", "min"),
            last_seen=("osm_timestamp", "max"),
            n_states=("state", "nunique"),
        )
        .reset_index()
    )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cams = load()

    mainland = cams[~cams["state"].isin(TERRITORIES)]
    states = sorted(mainland["state"].dropna().unique())
    print(f"  {len(states)} states/DC for panels; "
          f"{len(cams) - len(mainland)} territory rows excluded")

    shapes = {
        "zcta": geocode.load_shapes("zcta"),
        "county": geocode.load_shapes("county"),
        "place": geocode.load_shapes("place", states=states),
        "tract": geocode.load_shapes("tract", states=states),
    }
    joined = geocode.join_geographies(mainland, shapes)

    for col in LEVELS.values():
        print(f"  {col:12} {100 * joined[col].notna().mean():5.1f}% assigned")

    joined.drop(columns="geometry").to_parquet(
        OUT / "cameras_geocoded.parquet", index=False
    )

    for level in LEVELS:
        panel = aggregate(joined, level)
        panel.to_parquet(OUT / f"panel_geo_{level}.parquet", index=False)
        print(f"  panel_geo_{level}: {len(panel):,} rows")

    print(f"\nwrote outputs to {OUT}")


if __name__ == "__main__":
    main()
