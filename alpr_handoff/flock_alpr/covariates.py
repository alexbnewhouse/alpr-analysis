"""Stage 5 - ACS socioeconomic covariates and FBI agency-level crime counts.

This is the only stage that requires API keys:
  CENSUS_API_KEY   https://api.census.gov/data/key_signup.html
  FBI_API_KEY      https://api.data.gov/signup/
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from . import config, http

ACS_VARS = {
    # totals and medians
    "B01003_001E": "population",
    "B01002_001E": "median_age",
    "B19013_001E": "median_hh_income",
    "B19301_001E": "per_capita_income",
    "B19083_001E": "gini_index",
    "B25077_001E": "median_home_value",
    "B25064_001E": "median_gross_rent",
    # race / ethnicity (denominator B02001_001E)
    "B02001_001E": "race_total",
    "B02001_002E": "white_alone",
    "B02001_003E": "black_alone",
    "B02001_004E": "amerindian_alone",
    "B02001_005E": "asian_alone",
    "B02001_008E": "two_or_more",
    "B03003_003E": "hispanic",
    # nativity (denominator B05002_001E)
    "B05002_001E": "nativity_total",
    "B05002_013E": "foreign_born",
    # poverty (denominator B17001_001E)
    "B17001_001E": "poverty_universe",
    "B17001_002E": "poverty_count",
    # education, 25+ (denominator B15003_001E)
    "B15003_001E": "edu_total",
    "B15003_022E": "bachelors",
    "B15003_023E": "masters",
    "B15003_024E": "professional",
    "B15003_025E": "doctorate",
    # employment (denominator B23025_003E, civilian labor force)
    "B23025_003E": "civilian_labor_force",
    "B23025_005E": "unemployed",
    # tenure and vehicles (denominator B25003_001E / B25044_001E)
    "B25003_001E": "tenure_total",
    "B25003_002E": "owner_occupied",
    "B25003_003E": "renter_occupied",
    "B25044_001E": "vehicle_universe",
    "B25044_003E": "owner_no_vehicle",
    "B25044_010E": "renter_no_vehicle",
    # commute (denominator B08301_001E)
    "B08301_001E": "commute_total",
    "B08301_003E": "drove_alone",
    "B08301_010E": "public_transit",
}

# level -> (for-clause, in-clause). A None in-clause means a single national
# call; "state:*" is accepted nationally; tract must be requested one state at
# a time, which PER_STATE_LEVELS marks.
GEO_CLAUSE = {
    "zcta": ("zip code tabulation area:*", None),
    "place": ("place:*", "state:*"),
    "county": ("county:*", "state:*"),
    "tract": ("tract:*", "state:{fips}"),
}
PER_STATE_LEVELS = {"tract"}

# Census uses large negative jam values for suppressed/unavailable estimates.
SENTINELS = {-666666666, -999999999, -888888888, -222222222, -333333333}


def require_key(env_name: str, signup_url: str) -> str:
    val = os.environ.get(env_name)
    if not val:
        raise RuntimeError(
            f"{env_name} is not set. Get a free key at {signup_url} "
            f"then run: export {env_name}=<your key>"
        )
    return val


def parse_acs(payload: bytes, geo_col: str) -> pd.DataFrame:
    rows = json.loads(payload)
    df = pd.DataFrame(rows[1:], columns=rows[0])
    df = df.rename(columns=ACS_VARS)

    geo_cols = [c for c in ("zip code tabulation area", "place", "county",
                            "state", "tract")
                if c in df.columns]

    if geo_col == "zcta" and "zip code tabulation area" in df.columns:
        df["zcta"] = df["zip code tabulation area"]
    elif geo_col == "county" and {"state", "county"} <= set(df.columns):
        df["county_fips"] = df["state"] + df["county"]
    elif geo_col == "place" and {"state", "place"} <= set(df.columns):
        df["place_geoid"] = df["state"] + df["place"]
    elif geo_col == "tract" and {"state", "county", "tract"} <= set(df.columns):
        # 11-char GEOID: 2 state + 3 county + 6 tract. Tract nests in county,
        # which is exactly why it beats ZCTA for fixed-effects models.
        df["tract_geoid"] = df["state"] + df["county"] + df["tract"]

    for name in ACS_VARS.values():
        if name in df.columns:
            df[name] = pd.to_numeric(df[name], errors="coerce")
            df.loc[df[name].isin(SENTINELS), name] = pd.NA

    return df.drop(columns=geo_cols)


# (output name, numerator column(s), denominator column)
# Each share uses its OWN ACS universe, not total population -- education is
# over adults 25+, poverty over the population for whom status is determined,
# commute over workers. Dividing everything by total population silently
# understates every rate and by a different factor in each tract.
RATE_SPECS = [
    ("pct_white", ["white_alone"], "race_total"),
    ("pct_black", ["black_alone"], "race_total"),
    ("pct_amerindian", ["amerindian_alone"], "race_total"),
    ("pct_asian", ["asian_alone"], "race_total"),
    ("pct_two_or_more", ["two_or_more"], "race_total"),
    ("pct_hispanic", ["hispanic"], "race_total"),
    ("pct_foreign_born", ["foreign_born"], "nativity_total"),
    ("pct_below_poverty", ["poverty_count"], "poverty_universe"),
    ("pct_bachelors_plus",
     ["bachelors", "masters", "professional", "doctorate"], "edu_total"),
    ("pct_unemployed", ["unemployed"], "civilian_labor_force"),
    ("pct_owner_occupied", ["owner_occupied"], "tenure_total"),
    ("pct_renter_occupied", ["renter_occupied"], "tenure_total"),
    ("pct_no_vehicle", ["owner_no_vehicle", "renter_no_vehicle"],
     "vehicle_universe"),
    ("pct_drove_alone", ["drove_alone"], "commute_total"),
    ("pct_public_transit", ["public_transit"], "commute_total"),
]


def derive_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert ACS counts into shares, each over its correct ACS universe."""
    out = df.copy()
    for name, numerators, denominator in RATE_SPECS:
        if denominator not in out.columns:
            continue
        present = [n for n in numerators if n in out.columns]
        if not present:
            continue
        num = out[present].sum(axis=1, min_count=1)
        den = out[denominator].replace(0, pd.NA)
        out[name] = num / den
    return out


def _acs_call(level, for_clause, in_clause, year, key, force):
    params = {"get": "NAME," + ",".join(ACS_VARS), "for": for_clause, "key": key}
    if in_clause:
        params["in"] = in_clause
    payload = http.fetch(
        config.CENSUS_ACS_URL.format(year=year), params=params,
        force=force, timeout=300,
    )
    return parse_acs(payload, level)


def fetch_acs(level: str, year: int = 2023, force=False, states=None) -> pd.DataFrame:
    """ACS 5-year estimates for one geography level.

    Tract must be requested one state at a time -- the Census API rejects
    `in=state:*` for tract -- so those calls are looped and concatenated.
    """
    key = require_key("CENSUS_API_KEY", config.CENSUS_KEY_SIGNUP)
    for_clause, in_clause = GEO_CLAUSE[level]

    if level in PER_STATE_LEVELS:
        frames = []
        for st in (states or config.STATES):
            fips = config.STATE_FIPS[st]
            try:
                frames.append(_acs_call(
                    level, for_clause, in_clause.format(fips=fips), year, key, force
                ))
            except RuntimeError as exc:
                print(f"  acs_{level} {st}: {exc}")
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        df = _acs_call(level, for_clause, in_clause, year, key, force)

    df = derive_rates(df)
    df["acs_year"] = year
    df.to_parquet(config.INTERIM / f"acs_{level}.parquet", index=False)
    print(f"  acs_{level}: {len(df)} rows")
    return df


OFFENSES = ("violent-crime", "property-crime")


def fetch_agencies(states=None, force=False) -> pd.DataFrame:
    """Agency roster with ORI, station coordinates, county name, and type.

    The FBI publishes this per state, which removes the need for an external
    ORI-to-geography crosswalk (LEAIC). Note the coordinates locate the
    *station*, not the jurisdiction boundary -- adequate for assigning a city
    police department to its municipality, but not a substitute for a
    jurisdiction polygon.
    """
    key = require_key("FBI_API_KEY", config.FBI_KEY_SIGNUP)
    rows = []
    for st in (states or config.STATES):
        url = f"{config.FBI_CDE_URL}/agency/byStateAbbr/{st}"
        try:
            payload = http.fetch(url, params={"API_KEY": key}, force=force,
                                 timeout=180)
        except RuntimeError as exc:
            print(f"  agencies {st}: {exc}")
            continue
        data = json.loads(payload)
        for group in (data.values() if isinstance(data, dict) else [data]):
            if isinstance(group, list):
                rows.extend(group)

    df = pd.DataFrame(rows)
    if len(df):
        df = df.rename(columns={"ori": "ori9", "counties": "county_name",
                                "agency_type_name": "agency_type"})
        df = df.drop_duplicates("ori9")
        df.to_parquet(config.INTERIM / "fbi_agencies.parquet", index=False)
    print(f"  agencies: {len(df)} across {df['state_abbr'].nunique() if len(df) else 0} states")
    return df


def parse_crime(payload: bytes, ori: str, offense: str) -> pd.DataFrame:
    """Parse an FBI CDE summarized-agency response into agency-YEAR rows.

    Real response shape (verified against the live API):

        {"offenses": {"actuals": {"<Agency> Offenses":   {"01-2022": 12, ...},
                                  "<Agency> Clearances": {"01-2022":  3, ...}}}}

    Buckets are monthly ("MM-YYYY"); they are summed to calendar years. A month
    that is null counts as missing, not zero, so a partially-reported year is
    not silently understated -- ``months_reported`` records the count.
    """
    data = json.loads(payload)
    actuals = data.get("offenses", {}).get("actuals", {})
    offense_key = next((k for k in actuals if k.endswith("Offenses")), None)
    clear_key = next((k for k in actuals if k.endswith("Clearances")), None)
    if offense_key is None:
        return pd.DataFrame(columns=["ori9", "year", "offense", "actual",
                                     "cleared", "months_reported"])

    per_year = {}
    for bucket, value in actuals[offense_key].items():
        year = int(bucket.split("-")[1])
        rec = per_year.setdefault(year, {"actual": 0, "cleared": 0, "months": 0})
        if value is not None:
            rec["actual"] += value
            rec["months"] += 1
    if clear_key:
        for bucket, value in actuals[clear_key].items():
            year = int(bucket.split("-")[1])
            if year in per_year and value is not None:
                per_year[year]["cleared"] += value

    rows = [{"ori9": ori, "year": y, "offense": offense,
             "actual": r["actual"], "cleared": r["cleared"],
             "months_reported": r["months"]}
            for y, r in sorted(per_year.items())]
    return pd.DataFrame(rows)


def fetch_crime(oris, since=2018, until=2024, force=False, workers=8,
                offenses=OFFENSES) -> pd.DataFrame:
    """Agency-level offence counts, one request per (ORI, offence).

    Requests are latency-bound at roughly 1/s each, so a national pull is
    parallelised. The api.data.gov limit observed on this key is 10 requests
    per second, so the worker count is held below that; each response is
    cached to its own file, which keeps the writes independent.
    """
    key = require_key("FBI_API_KEY", config.FBI_KEY_SIGNUP)
    jobs = [(ori, off) for ori in oris for off in offenses]
    frames, failed = [], []
    done = 0

    def one(job):
        ori, offense = job
        url = f"{config.FBI_CDE_URL}/summarized/agency/{ori}/{offense}"
        payload = http.fetch(
            url,
            params={"from": f"01-{since}", "to": f"12-{until}", "API_KEY": key},
            force=force, timeout=120,
        )
        return parse_crime(payload, ori, offense)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, j): j for j in jobs}
        for fut in as_completed(futures):
            done += 1
            ori, offense = futures[fut]
            try:
                frames.append(fut.result())
            except Exception as exc:
                # Record WHICH request failed and why. A bare count cannot
                # distinguish "this agency reports no data" from "a whole
                # state timed out", and those bias coverage very differently.
                failed.append({"ori9": ori, "offense": offense,
                               "error": str(exc)[:200]})
            if done % 2000 == 0:
                print(f"  {done}/{len(jobs)} requests ({len(failed)} failed)")

    if failed:
        fdf = pd.DataFrame(failed)
        fdf.to_parquet(config.INTERIM / "crime_fetch_failures.parquet",
                       index=False)
        print(f"  {len(fdf)} failures logged -> crime_fetch_failures.parquet")

    long = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not len(long):
        print(f"  crime: no rows ({len(failed)} failed requests)")
        return long

    wide = long.pivot_table(index=["ori9", "year"], columns="offense",
                            values=["actual", "cleared"], aggfunc="sum")
    wide.columns = [f"{a}_{b}".replace("-", "_") for a, b in wide.columns]
    wide = wide.reset_index()
    months = (long.groupby(["ori9", "year"])["months_reported"]
              .max().reset_index())
    wide = wide.merge(months, on=["ori9", "year"], how="left")
    wide.to_parquet(config.INTERIM / "crime_by_ori.parquet", index=False)
    print(f"  crime: {len(wide)} agency-year rows ({len(failed)} failed requests)")
    return wide


def run(force=False):
    from .build_panel import LEVELS
    for level in LEVELS:
        fetch_acs(level, force=force)

    aos = pd.read_parquet(config.RAW / "aos_alpr_agencies.parquet")
    oris = sorted(aos.loc[aos["ori9"].notna(), "ori9"].unique())
    fetch_crime(oris, force=force)
