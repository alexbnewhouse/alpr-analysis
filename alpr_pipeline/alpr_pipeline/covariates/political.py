"""Political covariates: election returns and subnational ideology.

Three sources, all public-domain/CC0 and all reachable with a plain GET -- no
API key, no account, no guestbook:

* **VEST precinct-to-census reallocation** (Harvard Dataverse 10.7910/DVN/Z8TSH3)
  Precinct returns apportioned onto census block groups and tracts. This is the
  standout source for this project: because cameras already carry a tract and
  block-group GEOID, it reduces to a string join. No shapefiles, no spatial
  work, no fuzzy name matching, at ~800 m resolution.
* **MEDSL county presidential returns** (10.7910/DVN/VOQCHQ), 2000-2024.
  Revealed partisanship over seven elections, so you get trend and swing rather
  than just level. NOTE: this file sits behind a Dataverse *guestbook* -- see
  `fetch_medsl_county` before using it.
* **American Ideology Project** (10.7910/DVN/BQKU4M). MRP-estimated latent
  ideology at county *and place* level -- the place file is what lets you say
  something about the municipalities the `operator` tag names.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

DATAVERSE = "https://dataverse.harvard.edu/api/access/datafile"
USER_AGENT = "alpr-research-pipeline/1.0 (academic research)"

# --- file ids on Harvard Dataverse, verified reachable ---------------------
VEST_REALLOC_CONTIG_US = 11111135   # "Contiguous USA - Main Method" (~111 MB)
AIP_COUNTIES = 6690216              # aip_counties_ideology_v2022a.tab
AIP_PLACES = 6690205                # aip_cities_ideology_v2022a.tab
MEDSL_COUNTYPRES = 13573089         # countypres_2000-2024.tab (guestbook!)
MEDSL_GUESTBOOK_ID = 458

# Keyless mirror of MEDSL county presidential returns, 2000-2016 only. No
# guestbook, no identifying information submitted anywhere.
MEDSL_GITHUB_2000_2016 = (
    "https://raw.githubusercontent.com/MEDSL/county-returns/master/"
    "countypres_2000-2016.csv"
)


def _get(url: str, dest: Path, timeout: float = 1800) -> Path:
    """Download to `dest` unless already cached."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading %s", url)
    with requests.get(url, stream=True, timeout=timeout,
                      headers={"User-Agent": USER_AGENT}) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    log.info("Cached %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


# --- VEST reallocated returns ---------------------------------------------

def fetch_vest_reallocated(cache_dir: Path, level: str = "tract",
                           year: int = 2020) -> pd.DataFrame:
    """Precinct returns reallocated onto census geography.

    Returns a frame keyed `geoid` with two-party vote counts and shares.
    `level` is "tract" or "bg"; `year` is 2016 or 2020.
    """
    if level not in ("tract", "bg"):
        raise ValueError("VEST reallocation is published for tract and bg only")
    if year not in (2016, 2020):
        raise ValueError("VEST reallocation covers 2016 and 2020")

    if year == 2016:
        log.warning(
            "The 2016 reallocation is built on 2010-vintage census geography: "
            "15.6%% of its tract GEOIDs do not exist in the 2020 vintage and it "
            "matches only ~71%% of 2023 ACS tracts. Do NOT join it to "
            "2020-vintage GEOIDs without a crosswalk, and do not difference it "
            "against 2020 to get a 'swing' -- that would measure boundary "
            "changes as much as politics."
        )

    zip_path = _get(f"{DATAVERSE}/{VEST_REALLOC_CONTIG_US}",
                    Path(cache_dir) / "vest_realloc_contig_us.zip")

    member = f"{'bg' if level == 'bg' else 'tracts'}-{year}-RLCR.csv"
    log.info("Reading %s from the reallocation archive", member)
    with zipfile.ZipFile(zip_path) as zf:
        name = next((n for n in zf.namelist() if n.endswith(member)), None)
        if name is None:
            raise FileNotFoundError(
                f"{member} not in archive; members: {zf.namelist()[:10]}"
            )
        with zf.open(name) as fh:
            df = pd.read_csv(fh, dtype={0: str}, low_memory=False)

    return _tidy_vest(df, level, year)


def _tidy_vest(df: pd.DataFrame, level: str, year: int) -> pd.DataFrame:
    """Reduce VEST's wide per-candidate columns to a compact partisan summary.

    Column names encode candidate initials per state (G20PRERTRU, G20PREDBID),
    so we select by the party letter in position 6 rather than by candidate.
    """
    geo_col = next(
        (c for c in df.columns if c.lower().startswith(("bg_geoid", "geoid",
                                                        "tract_geoid"))),
        df.columns[0],
    )
    yy = str(year)[2:]
    prefix = f"G{yy}PRE"

    dem = [c for c in df.columns if c.startswith(prefix + "D")]
    rep = [c for c in df.columns if c.startswith(prefix + "R")]
    oth = [c for c in df.columns
           if c.startswith(prefix) and c not in dem and c not in rep]

    if not dem or not rep:
        raise ValueError(
            f"No {prefix} D/R columns found; got {list(df.columns)[:15]}"
        )

    out = pd.DataFrame({"geoid": df[geo_col].astype(str).str.zfill(
        12 if level == "bg" else 11)})
    out[f"pres{year}_dem"] = df[dem].sum(axis=1, numeric_only=True)
    out[f"pres{year}_rep"] = df[rep].sum(axis=1, numeric_only=True)
    out[f"pres{year}_other"] = (
        df[oth].sum(axis=1, numeric_only=True) if oth else 0.0
    )
    total = out[[f"pres{year}_dem", f"pres{year}_rep",
                 f"pres{year}_other"]].sum(axis=1)
    out[f"pres{year}_total"] = total
    # Two-party share is the standard covariate; guard empty geographies.
    twoparty = out[f"pres{year}_dem"] + out[f"pres{year}_rep"]
    out[f"pres{year}_dem_share"] = (
        out[f"pres{year}_dem"].div(twoparty.where(twoparty > 0)) * 100
    )
    log.info("VEST %s %d: %d geographies", level, year, len(out))
    return out


# --- American Ideology Project --------------------------------------------

def fetch_aip(cache_dir: Path, level: str = "county") -> pd.DataFrame:
    """MRP-estimated ideology. `level` is "county" or "place"."""
    file_id = AIP_COUNTIES if level == "county" else AIP_PLACES
    path = _get(f"{DATAVERSE}/{file_id}",
                Path(cache_dir) / f"aip_{level}_ideology.tab")
    df = pd.read_csv(path, sep="\t", low_memory=False)

    key = "county_fips" if level == "county" else "place_fips"
    if key not in df.columns:
        raise ValueError(f"{key} not in AIP {level} file: {list(df.columns)[:15]}")

    width = 5 if level == "county" else 7
    df["geoid"] = df[key].astype("Int64").astype(str).str.zfill(width)

    keep = ["geoid", "survey_period", "mrp_ideology", "mrp_ideology_se",
            "self_ideology", "demshare_pres", "sample_size"]
    df = df[[c for c in keep if c in df.columns]]

    # Three overlapping survey periods per unit; keep the most recent so the
    # result is one row per geography.
    if "survey_period" in df.columns:
        df = (df.sort_values("survey_period")
                .groupby("geoid", as_index=False).last())

    log.info("AIP %s ideology: %d geographies", level, len(df))
    return df


# --- MEDSL county presidential returns ------------------------------------

def fetch_medsl_county_github(cache_dir: Path) -> pd.DataFrame:
    """County presidential returns 2000-2016 from MEDSL's GitHub mirror.

    Fully anonymous: no guestbook, no identifying information transmitted.
    Prefer this unless you specifically need 2020/2024.
    """
    path = _get(MEDSL_GITHUB_2000_2016,
                Path(cache_dir) / "medsl_countypres_2000_2016.csv")
    df = pd.read_csv(path, low_memory=False)
    return _tidy_medsl(df)


def fetch_medsl_county(cache_dir: Path, name: str, email: str,
                       institution: str, position: str = "Researcher"
                       ) -> pd.DataFrame:
    """County presidential returns 2000-2024 from Harvard Dataverse.

    **This transmits your name, email, institution, and position to Harvard
    Dataverse.** The file is behind a Dataverse guestbook, which MEDSL uses for
    download tracking; there is no anonymous route to the 2020/2024 data. The
    identifying arguments are therefore required rather than defaulted -- this
    call must be a deliberate act, not something a pipeline does silently.

    If you do not want to disclose that, use `fetch_medsl_county_github`
    (2000-2016) or the VEST reallocation, both of which are anonymous.
    """
    if not all([name, email, institution]):
        raise ValueError(
            "name, email and institution are required: this request submits "
            "them to a third party. Use fetch_medsl_county_github() to avoid it."
        )

    dest = Path(cache_dir) / "medsl_countypres_2000_2024.tab"
    if not dest.exists():
        log.warning("Submitting guestbook response (name/email/institution) "
                    "to dataverse.harvard.edu for guestbook %d",
                    MEDSL_GUESTBOOK_ID)
        resp = requests.post(
            f"{DATAVERSE}/{MEDSL_COUNTYPRES}",
            json={"guestbookResponse": {
                "name": name, "email": email,
                "institution": institution, "position": position,
            }},
            headers={"User-Agent": USER_AGENT,
                     "Content-Type": "application/json"},
            timeout=300,
        )
        resp.raise_for_status()
        signed = resp.json()["data"]["signedUrl"]
        _get(signed, dest)

    df = pd.read_csv(dest, sep="\t", low_memory=False)
    return _tidy_medsl(df)


def _tidy_medsl(df: pd.DataFrame) -> pd.DataFrame:
    """Long candidate rows -> one row per county-year with party shares."""
    df.columns = [c.lower() for c in df.columns]
    # The Dataverse release calls the key `county_fips`; the GitHub mirror of
    # the 2000-2016 file calls it `fips`. Accept either.
    fips_col = next((c for c in ("county_fips", "fips") if c in df.columns), None)
    if fips_col is None:
        raise ValueError(f"No county FIPS column in {list(df.columns)}")

    df = df[df[fips_col].notna()].copy()
    df["geoid"] = (df[fips_col].astype(float).astype("Int64")
                   .astype(str).str.zfill(5))

    party = df["party"].fillna("OTHER").str.upper()
    df["_party"] = party.where(party.isin(["DEMOCRAT", "REPUBLICAN"]), "OTHER")

    # Rows are split by voting mode in some years; sum them.
    grouped = (df.groupby(["geoid", "year", "_party"], as_index=False)
                 ["candidatevotes"].sum())
    wide = grouped.pivot_table(index=["geoid", "year"], columns="_party",
                               values="candidatevotes", fill_value=0)
    wide = wide.reset_index().rename(columns={
        "DEMOCRAT": "dem_votes", "REPUBLICAN": "rep_votes",
        "OTHER": "other_votes",
    })
    twoparty = wide.get("dem_votes", 0) + wide.get("rep_votes", 0)
    wide["dem_share"] = wide.get("dem_votes", 0).div(
        twoparty.where(twoparty > 0)) * 100

    log.info("MEDSL county returns: %d county-year rows, years %s",
             len(wide), sorted(wide["year"].unique()))
    return wide


def medsl_wide_by_year(medsl: pd.DataFrame,
                       years: tuple[int, ...] = (2016, 2020)) -> pd.DataFrame:
    """Pivot county-year returns to one row per county, columns per year."""
    out = pd.DataFrame({"geoid": sorted(medsl["geoid"].unique())})
    for year in years:
        sub = medsl[medsl["year"] == year][["geoid", "dem_share"]]
        out = out.merge(
            sub.rename(columns={"dem_share": f"dem_share_{year}"}),
            on="geoid", how="left",
        )
    if len(years) >= 2:
        a, b = years[0], years[-1]
        out[f"dem_swing_{a}_{b}"] = (
            out[f"dem_share_{b}"] - out[f"dem_share_{a}"]
        )
    return out
