"""Commercial-versus-residential land use, from LEHD LODES.

WHAT THIS MEASURES
------------------
How far a place is an employment/commercial district rather than a bedroom
neighbourhood, and how much of its activity is consumer-facing retail.

There is no national parcel-level land use file. The standard substitute in
urban economics is the balance between *jobs located in* an area and *people
living in* it. An area with many jobs and few residents is commercial; the
reverse is residential.

This matters here for two distinct reasons. Arterial-adjacent commercial strips
are where fixed ALPRs are typically mounted; and separately, roughly 14% of the
operator-tagged cameras in this data belong to retail chains (Lowe's, Home
Depot, Simon Property), whose siting is a corporate decision unrelated to local
policing. A retail-intensity measure lets that channel be controlled or split
out rather than silently pooled.

SOURCE
------
US Census Bureau, Longitudinal Employer-Household Dynamics (LEHD),
**LODES version 8**, 2022 vintage, published per state:

    WAC  jobs by WORKPLACE block
      https://lehd.ces.census.gov/data/lodes/LODES8/<st>/wac/<st>_wac_S000_JT00_2022.csv.gz
    RAC  workers by RESIDENCE block
      https://lehd.ces.census.gov/data/lodes/LODES8/<st>/rac/<st>_rac_S000_JT00_2022.csv.gz
    Geographic crosswalk (block -> tract / county / place / ZCTA)
      https://lehd.ces.census.gov/data/lodes/LODES8/<st>/<st>_xwalk.csv.gz

`S000` is all jobs; `JT00` is all job types. Blocks are 2020 vintage
(`tabblk2020`), and the crosswalk carries `trct`, `cty`, `stplc` and `zcta`,
so every analysis level is reached by aggregation rather than a spatial join.

Industry columns follow NAICS sectors; the two used here are
    CNS07  Retail Trade
    CNS18  Accommodation and Food Services
which together are the consumer-facing, parking-lot-bearing sectors.

CAVEATS
-------
LODES covers jobs reported through state unemployment insurance systems. It
therefore omits most self-employment, and its coverage of federal employment is
partial. Counts are noise-infused for confidentiality, which is immaterial when
aggregating blocks up to tracts but would matter at block level.
"""
import gzip
import io

import pandas as pd

from . import config, http

LODES_BASE = "https://lehd.ces.census.gov/data/lodes/LODES8"

# Preferred vintage first. Not every state publishes every year -- Michigan's
# most recent is 2021, and Alaska does not participate in LEHD at all -- so the
# year actually used is recorded per state and reported, rather than a state
# being silently dropped.
LODES_YEARS = (2022, 2021, 2020)

# Crosswalk column carrying each analysis level's key, and the width to pad to.
XWALK_KEYS = {
    "tract": ("trct", "tract_geoid", 11),
    "county": ("cty", "county_fips", 5),
    "place": ("stplc", "place_geoid", 7),
    "zcta": ("zcta", "zcta", 5),
}

# Consumer-facing sectors: retail trade, and accommodation & food services.
RETAIL_COLS = ["CNS07", "CNS18"]


def _read_gz_csv(url: str, usecols=None, dtype=None) -> pd.DataFrame:
    raw = http.fetch(url, timeout=600)
    with gzip.open(io.BytesIO(raw), "rt") as fh:
        return pd.read_csv(fh, usecols=usecols, dtype=dtype)


def load_state(state: str):
    """Block-level jobs, retail jobs and resident workers for one state.

    Returns (DataFrame, year_used). Falls back through LODES_YEARS so a state
    whose latest vintage is older is still included rather than dropped.
    """
    st = state.lower()
    last = None
    for year in LODES_YEARS:
        try:
            wac = _read_gz_csv(
                f"{LODES_BASE}/{st}/wac/{st}_wac_S000_JT00_{year}.csv.gz",
                usecols=["w_geocode", "C000"] + RETAIL_COLS,
                dtype={"w_geocode": str},
            ).rename(columns={"w_geocode": "block", "C000": "jobs_total"})
            rac = _read_gz_csv(
                f"{LODES_BASE}/{st}/rac/{st}_rac_S000_JT00_{year}.csv.gz",
                usecols=["h_geocode", "C000"],
                dtype={"h_geocode": str},
            ).rename(columns={"h_geocode": "block", "C000": "resident_workers"})
        except RuntimeError as exc:
            last = exc
            continue

        wac["jobs_retail_food"] = wac[RETAIL_COLS].sum(axis=1)
        wac = wac[["block", "jobs_total", "jobs_retail_food"]]
        return wac.merge(rac, on="block", how="outer").fillna(0), year

    raise RuntimeError(f"{state}: no LODES vintage available ({last})")


def load_crosswalk(state: str) -> pd.DataFrame:
    st = state.lower()
    cols = ["tabblk2020"] + [c for c, _, _ in XWALK_KEYS.values()]
    xw = _read_gz_csv(f"{LODES_BASE}/{st}/{st}_xwalk.csv.gz",
                      usecols=cols, dtype=str)
    return xw.rename(columns={"tabblk2020": "block"})


def build(level: str, states=None, verbose=True) -> pd.DataFrame:
    """Land-use measures for every unit at one geography level.

        jobs_total            jobs located in the unit
        jobs_retail_food      of which retail trade + accommodation/food
        resident_workers      employed people living in the unit
        pct_jobs_retail_food  retail share of local jobs
        jobs_per_resident_worker   jobs / resident workers -- the jobs-housing
                              balance; > 1 means a net importer of commuters
        employment_ratio      jobs / (jobs + resident workers), bounded 0-1;
                              0 is purely residential, 1 purely employment
    """
    src_col, out_key, width = XWALK_KEYS[level]
    frames, vintages, missing = [], {}, []
    for state in (states or config.STATES):
        try:
            blocks, year = load_state(state)
            xw = load_crosswalk(state)
        except RuntimeError as exc:
            missing.append(state)
            print(f"  {state}: EXCLUDED - {exc}")
            continue
        vintages[state] = year
        merged = blocks.merge(xw[["block", src_col]], on="block", how="inner")
        merged = merged[merged[src_col].notna() & (merged[src_col] != "")]
        agg = (merged.groupby(src_col, as_index=False)
               [["jobs_total", "jobs_retail_food", "resident_workers"]].sum())
        frames.append(agg)
        if verbose:
            print(f"  {state}: {len(agg):,} {level}s, "
                  f"{int(agg['jobs_total'].sum()):,} jobs")

    if not frames:
        raise RuntimeError("no LODES data assembled")

    # A ZCTA or place can straddle a state line and appear in two states' files.
    out = (pd.concat(frames, ignore_index=True)
           .groupby(src_col, as_index=False)
           [["jobs_total", "jobs_retail_food", "resident_workers"]].sum()
           .rename(columns={src_col: out_key}))
    out[out_key] = out[out_key].astype(str).str.zfill(width)

    jobs = out["jobs_total"].replace(0, pd.NA)
    workers = out["resident_workers"].replace(0, pd.NA)
    out["pct_jobs_retail_food"] = out["jobs_retail_food"] / jobs
    out["jobs_per_resident_worker"] = out["jobs_total"] / workers
    denom = (out["jobs_total"] + out["resident_workers"]).replace(0, pd.NA)
    out["employment_ratio"] = out["jobs_total"] / denom

    dest = config.INTERIM / f"landuse_{level}.parquet"
    out.to_parquet(dest, index=False)

    older = {s: y for s, y in vintages.items() if y != LODES_YEARS[0]}
    print(f"  {level}: {len(out):,} units, "
          f"{int(out['jobs_total'].sum()):,} jobs -> {dest}")
    if older:
        print(f"    non-current vintage: {older}")
    if missing:
        print(f"    NO DATA (excluded entirely): {' '.join(missing)}")
    return out
