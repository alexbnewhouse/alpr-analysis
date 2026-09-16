"""Stage 1 - device-level ALPR nodes from OpenStreetMap via Overpass.

Extracts every node tagged ``surveillance:type=ALPR`` regardless of
manufacturer. Filtering to Flock Safety is a downstream concern; the non-Flock
nodes are a useful comparison group.
"""
import json
import time

import pandas as pd

from . import config, http

TAGS = {
    "man_made": "man_made",
    "manufacturer": "manufacturer",
    "brand": "brand",
    "surveillance:manufacturer": "surveillance_manufacturer",
    "surveillance:brand": "surveillance_brand",
    "operator": "operator",
    "surveillance:operator": "surveillance_operator",
    "operator:type": "operator_type",
    "camera:type": "camera_type",
    "camera:mount": "camera_mount",
    "direction": "direction",
    "camera:direction": "camera_direction",
    "surveillance": "surveillance",
    "surveillance:zone": "surveillance_zone",
    "check_date": "check_date",
    "wikimedia_commons": "wikimedia_commons",
}

# Vendor is spread across several tags depending on who mapped the node.
# In California alone, 744 nodes carry brand=Flock Safety with no manufacturer
# tag at all -- a 5% undercount if only `manufacturer` is consulted. Because
# tagging convention varies by mapper and region, that error is not random
# across geographies, so it must not be allowed to reach the dependent variable.
VENDOR_KEYS = [
    "manufacturer", "brand", "surveillance_manufacturer", "surveillance_brand",
]

COLUMNS = [
    "osm_id", "lat", "lon", "state", "osm_version", "osm_timestamp", "vendor",
] + list(TAGS.values())


def coalesce_vendor(df: pd.DataFrame) -> pd.Series:
    """First non-empty vendor tag, in priority order."""
    out = pd.Series([None] * len(df), index=df.index, dtype="object")
    for key in VENDOR_KEYS:
        if key in df.columns:
            out = out.fillna(df[key].replace("", None))
    return out


def is_flock(vendor: pd.Series) -> pd.Series:
    return vendor.fillna("").str.contains("Flock", case=False)


def build_query(state: str) -> str:
    """Overpass QL for all ALPR nodes inside one US state boundary."""
    return (
        "[out:json][timeout:300];\n"
        f'area["ISO3166-2"="US-{state}"][admin_level=4]->.a;\n'
        'node(area.a)["surveillance:type"="ALPR"];\n'
        "out tags center meta;"
    )


def parse_overpass(payload: bytes, state: str) -> pd.DataFrame:
    elements = json.loads(payload)["elements"]
    rows = []
    for e in elements:
        tags = e.get("tags", {})
        center = e.get("center") or {}
        row = {
            "osm_id": e["id"],
            "lat": e.get("lat", center.get("lat")),
            "lon": e.get("lon", center.get("lon")),
            "state": state,
            "osm_version": e.get("version"),
            "osm_timestamp": e.get("timestamp"),
        }
        for src, dst in TAGS.items():
            row[dst] = tags.get(src)
        rows.append(row)

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["osm_timestamp"] = pd.to_datetime(df["osm_timestamp"], errors="coerce", utc=True)
    df["osm_version"] = pd.to_numeric(df["osm_version"], errors="coerce").astype("Int64")
    df["vendor"] = coalesce_vendor(df)
    return df


STATE_DIR = config.RAW / "states"


def fetch_state(state: str, force=False) -> pd.DataFrame:
    """Fetch and parse one state, checkpointing the result to its own file.

    A completed state is never re-fetched unless force=True, so an interrupted
    national run resumes instead of restarting.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint = STATE_DIR / f"{state}.parquet"
    if checkpoint.exists() and not force:
        if not _served_by_mirror(checkpoint):
            return pd.read_parquet(checkpoint)
        print(f"    {state}: checkpoint came from a mirror, retrying primary")

    query = build_query(state).encode()
    last = None
    for url in config.OVERPASS_MIRRORS:
        try:
            payload = http.fetch(
                url, method="POST", data=query, force=force, timeout=300
            )
            break
        except RuntimeError as exc:
            last = exc
            print(f"    {state}: {url.split('/')[2]} unavailable, trying next mirror")
    else:
        raise RuntimeError(f"all Overpass mirrors failed for {state}: {last}")

    df = parse_overpass(payload, state)
    df["source_endpoint"] = url
    df.to_parquet(checkpoint, index=False)
    return df


def _served_by_mirror(checkpoint) -> bool:
    """True if a checkpoint was filled from a non-primary endpoint.

    Mirrors lag the main Overpass database, sometimes badly: kumi.systems
    returned 1,526 Pennsylvania nodes when the primary had 2,347, a 35%
    shortfall. A failed request is visible; a short response is not. So
    mirror-sourced checkpoints are provisional and get retried against the
    primary on the next run.
    """
    try:
        head = pd.read_parquet(checkpoint, columns=["source_endpoint"])
    except (KeyError, ValueError, OSError):
        return True  # written before endpoints were recorded; treat as suspect
    if not len(head):
        return False
    return head["source_endpoint"].iloc[0] != config.OVERPASS_MIRRORS[0]


def run(states=None, force=False, pause=2.0) -> pd.DataFrame:
    """Extract every state, tolerating individual failures.

    Overpass returns 504 under load. One state failing must not discard the
    states already collected, so failures are recorded and reported rather
    than raised.
    """
    targets = states or config.STATES
    frames, failed = [], []

    for state in targets:
        cached = (STATE_DIR / f"{state}.parquet").exists() and not force
        try:
            df = fetch_state(state, force=force)
        except RuntimeError as exc:
            print(f"  {state}: FAILED - {exc}")
            failed.append(state)
            continue

        flock = is_flock(df["vendor"]).sum()
        mark = "(cached)" if cached else ""
        print(f"  {state}: {len(df):>6} ALPR nodes ({flock} Flock) {mark}")
        frames.append(df)
        if not cached:
            time.sleep(pause)

    if not frames:
        raise RuntimeError("no states extracted successfully")

    # Drop empty states (Alaska has none) before concat: all-NA frames would
    # otherwise muddy the result dtypes.
    non_empty = [f for f in frames if len(f)]
    out = pd.concat(non_empty, ignore_index=True)
    out.to_parquet(config.RAW / "osm_alpr_nodes.parquet", index=False)
    print(f"wrote {len(out)} nodes from {len(frames)} states "
          f"-> {config.RAW / 'osm_alpr_nodes.parquet'}")

    if "source_endpoint" in out.columns:
        primary = config.OVERPASS_MIRRORS[0]
        mirrored = sorted(out.loc[out["source_endpoint"] != primary, "state"].unique())
        if mirrored:
            print(f"WARNING: {len(mirrored)} states served by a mirror and may be "
                  f"undercounted: {' '.join(mirrored)}")
            print("re-run to retry them against the primary endpoint")

    if failed:
        print(f"FAILED states ({len(failed)}): {' '.join(failed)}")
        print("re-run the same command to retry only these")
    return out
