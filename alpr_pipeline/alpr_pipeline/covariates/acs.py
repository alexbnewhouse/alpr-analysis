"""Download and reduce ACS 5-year table-based summary files.

Why these files and not the Census API: as of 2026 the API redirects every
un-keyed request to a "Missing Key" page, so an API-based pipeline cannot run
unattended without the user registering for a key. The table-based summary
files at www2.census.gov are plain HTTP, no key, no rate limit, and carry every
geography in one file per table.

The trade-off is size -- B17001 alone is 113 MB because it ships 59 columns for
all 380k+ geographies. So each table is streamed and reduced on the fly to just
the requested summary level and the columns some Measure actually needs, then
cached as Parquet. Nothing large is ever held in memory or written to disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests

from .variables import MEASURES, Measure, SUMMARY_LEVELS, tables_needed

log = logging.getLogger(__name__)

ACS_YEAR = 2023
BASE_URL = (
    "https://www2.census.gov/programs-surveys/acs/summary_file/{year}/"
    "table-based-SF/data/5YRData/acsdt5y{year}-{table}.dat"
)
USER_AGENT = "alpr-research-pipeline/1.0 (academic research)"


def _table_url(table: str, year: int = ACS_YEAR) -> str:
    return BASE_URL.format(year=year, table=table.lower())


def fetch_table(table: str, columns: set[str], level: str,
                cache_dir: Path, year: int = ACS_YEAR,
                force: bool = False) -> pd.DataFrame:
    """Stream one ACS table, keeping only `level` rows and `columns` columns.

    Returns a DataFrame indexed by the bare FIPS GEOID (no "1400000US" prefix),
    so it joins directly against the GEOIDs on the camera table.
    """
    sl = SUMMARY_LEVELS[level]
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"acs{year}_{table.lower()}_{level}.parquet"

    if cache_path.exists() and not force:
        return pd.read_parquet(cache_path)

    url = _table_url(table, year)
    log.info("Streaming %s (%s level) from %s", table, level, url)

    resp = requests.get(url, stream=True, timeout=600,
                        headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    # The server sends no charset, so requests leaves `encoding` unset and
    # iter_lines(decode_unicode=True) would yield bytes. Declare it.
    resp.encoding = resp.encoding or "utf-8"

    prefix = sl.code + "US"
    header: list[str] | None = None
    keep_idx: list[int] = []
    keep_names: list[str] = []
    geoids: list[str] = []
    rows: list[list[float | None]] = []
    scanned = 0

    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if header is None:
            header = raw.split("|")
            for i, name in enumerate(header):
                if name in columns:
                    keep_idx.append(i)
                    keep_names.append(name)
            missing = columns - set(keep_names)
            if missing:
                raise ValueError(
                    f"Table {table} is missing expected columns {sorted(missing)}. "
                    f"ACS may have renumbered this table for {year}."
                )
            continue

        scanned += 1
        if not raw.startswith(prefix):
            continue
        parts = raw.split("|")
        geoids.append(parts[0].split("US", 1)[1])
        rows.append([_to_number(parts[i]) for i in keep_idx])

    df = pd.DataFrame(rows, columns=keep_names)
    df.insert(0, "geoid", geoids)

    if df.empty:
        # Not an error: many detailed tables are simply not published at block
        # group. The caller decides whether that is fatal.
        log.warning("Table %s has NO rows at %s level (scanned %d rows). "
                    "This table is likely not published at that geography.",
                    table, level, scanned)
    else:
        log.info("  %s: %d %s rows kept (of %d scanned)",
                 table, len(df), level, scanned)

    df.to_parquet(cache_path, index=False)
    return df


def _to_number(value: str) -> float | None:
    """ACS uses empty strings and jam values for suppressed/absent estimates.

    Negative jam codes (-666666666 and friends) mean "estimate not available",
    not a real negative dollar amount, so they must become NULL rather than
    silently dragging a mean downward.
    """
    value = value.strip()
    if not value:
        return None
    try:
        num = float(value)
    except ValueError:
        return None
    if num <= -222222222:
        return None
    return num


def build_covariates(level: str, cache_dir: Path,
                     measures: list[Measure] | None = None,
                     year: int = ACS_YEAR, force: bool = False) -> pd.DataFrame:
    """Assemble every measure for one summary level into a single wide frame."""
    measures = measures or MEASURES
    needed = tables_needed(measures)

    frames: dict[str, pd.DataFrame] = {}
    for table, columns in sorted(needed.items()):
        frames[table] = fetch_table(table, columns, level, cache_dir, year, force)

    # Start from the widest table so no geography is dropped by the join order.
    base_geoids: set[str] = set()
    for df in frames.values():
        base_geoids.update(df["geoid"])
    out = pd.DataFrame({"geoid": sorted(base_geoids)})

    unavailable: list[str] = []
    for m in measures:
        src = frames[m.table]
        if src.empty:
            unavailable.append(m.name)
            out[m.name] = pd.NA
            continue

        merged = out[["geoid"]].merge(src, on="geoid", how="left")
        num = sum(merged[f"{m.table}_E{n:03d}"] for n in m.numerator)
        if m.is_ratio:
            den = merged[f"{m.table}_E{m.denominator:03d}"]
            # A zero universe is "no one to be a percentage of", not 0%.
            value = num.where(den > 0).div(den.where(den > 0)) * m.scale
        else:
            value = num * m.scale
        out[m.name] = value.values

    if unavailable:
        log.warning("Not published at %s level, left NULL: %s",
                    level, ", ".join(unavailable))

    log.info("Built %d covariate rows x %d measures at %s level",
             len(out), len(measures), level)
    return out
