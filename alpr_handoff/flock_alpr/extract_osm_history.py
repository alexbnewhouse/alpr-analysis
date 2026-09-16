"""Stage 2 - quarterly OSM discovery series with mapping-effort denominators.

IMPORTANT: the counts here measure when volunteers *mapped* a camera, not when
it was *installed*. The column is therefore named ``discovery_count`` and never
``installed_count``.

To make that bias measurable rather than merely disclaimed, two denominators
are pulled over the identical polygons and time steps:

  ``total_nodes``   - all OSM nodes, i.e. general mapping intensity
  ``contributors``  - distinct contributions to ALPR nodes

Normalising ``discovery_count`` by these answers "did ALPR mapping move
independently of overall OSM effort in this place?".
"""
import json
import time

import pandas as pd

from . import config, http

ALPR_FILTER = "surveillance:type=ALPR and type:node"

# (column name, endpoint, ohsome filter)
SERIES = [
    ("discovery_count", "/elements/count/groupBy/boundary", ALPR_FILTER),
    ("total_nodes", "/elements/count/groupBy/boundary", "type:node"),
    ("contributors", "/contributions/count/groupBy/boundary", ALPR_FILTER),
]

OUT_COLS = [
    "region", "quarter", "quarter_complete",
    "discovery_count", "total_nodes", "contributors",
]


def data_window():
    """Valid temporal extent of the ohsome history database, as (lo, hi) dates."""
    meta = json.loads(http.fetch(f"{config.OHSOME_URL}/metadata"))
    extent = meta["extractRegion"]["temporalExtent"]
    return extent["fromTimestamp"][:10], extent["toTimestamp"][:10]


def clamp_window(start, end, lo, hi):
    return (max(start, lo), min(end, hi))


def parse_series(payload: bytes, value_name: str) -> pd.DataFrame:
    """Parse a flat (ungrouped) ohsome time series."""
    result = json.loads(payload)["result"]
    df = pd.DataFrame(result).rename(columns={"value": value_name})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[["timestamp", value_name]]


def parse_grouped_series(payload: bytes, value_name: str) -> pd.DataFrame:
    """Parse an ohsome groupBy/boundary response into long form.

    Two response shapes exist. ``/elements/count`` is a *snapshot* series and
    labels each point with ``timestamp``. ``/contributions/count`` is a *flow*
    series over half-open intervals and labels each point with
    ``fromTimestamp``/``toTimestamp``.

    Both are keyed here on the interval start, so a row reads: stock at the
    start of the quarter, alongside contributions made during that quarter.
    """
    groups = json.loads(payload)["groupByResult"]
    rows = []
    for g in groups:
        region = g["groupByObject"]
        for point in g["result"]:
            stamp = point.get("timestamp", point.get("fromTimestamp"))
            if stamp is None:
                raise ValueError(f"ohsome point lacks a timestamp key: {point}")
            rows.append({
                "region": region,
                "timestamp": stamp,
                value_name: point["value"],
            })
    df = pd.DataFrame(rows, columns=["region", "timestamp", value_name])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def mark_complete_quarters(df: pd.DataFrame, hi: str, interval="P3M") -> pd.DataFrame:
    """Flag quarters whose interval extends past the end of the ohsome database.

    The last quarter is nearly always partial: its flow measures (contributors)
    cover less time than a full quarter and are not comparable to earlier rows.
    Marked rather than dropped, so the caller decides.
    """
    months = int(interval.strip("PM")) if interval.startswith("P") else 3
    end = pd.Timestamp(hi, tz="UTC")
    out = df.copy()
    quarter_end = out["timestamp"] + pd.DateOffset(months=months)
    out["quarter_complete"] = quarter_end <= end
    return out


def run(bpolys: dict, start="2023-01-01", interval="P3M", force=False,
        pause=1.0) -> pd.DataFrame:
    """Fetch all three series for a GeoJSON FeatureCollection of regions.

    Each feature must carry an ``id`` property; ohsome echoes it back as the
    group key.
    """
    lo, hi = data_window()
    s, e = clamp_window(start, hi, lo, hi)
    print(f"  ohsome window {s} -> {e} (db covers {lo}..{hi})")

    bpolys_json = json.dumps(bpolys)
    merged = None
    for name, endpoint, filt in SERIES:
        payload = http.fetch(
            config.OHSOME_URL + endpoint, method="POST",
            data={"bpolys": bpolys_json, "filter": filt,
                  "time": f"{s}/{e}/{interval}"},
            force=force, timeout=600,
        )
        part = parse_grouped_series(payload, name)
        merged = part if merged is None else merged.merge(
            part, on=["region", "timestamp"], how="outer"
        )
        print(f"  {name}: {len(part)} region-quarters")
        time.sleep(pause)

    # Mark before renaming: mark_complete_quarters reads `timestamp`.
    out = mark_complete_quarters(merged, hi, interval)
    out = out.rename(columns={"timestamp": "quarter"})[OUT_COLS]
    out = out.sort_values(["region", "quarter"]).reset_index(drop=True)

    partial = int((~out["quarter_complete"]).sum())
    if partial:
        print(f"  {partial} rows are partial quarters (quarter_complete=False)")
    out.to_parquet(config.RAW / "osm_alpr_history.parquet", index=False)
    print(f"wrote {len(out)} rows -> {config.RAW / 'osm_alpr_history.parquet'}")
    return out
