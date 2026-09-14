"""Crime covariates from FBI UCR "Offenses Known and Clearances by Arrest".

Source: Jacob Kaplan's cleaned concatenation of the FBI's Summary Reporting
System, Harvard Dataverse ``doi:10.7910/DVN/OESSD1``, CC BY 4.0. Cite Kaplan,
not just the FBI.

Why this and not the FBI's own API: the Crime Data Explorer API at
``api.usa.gov`` requires an ``api.data.gov`` key on every call, and the S3
bucket that used to serve CDE bulk files is gone (``NoSuchBucket``). Kaplan's
archive is gated by a Dataverse guestbook instead -- a disclosure, but no
credential to manage. See :mod:`.dataverse`.

**Granularity.** UCR is reported by *agency* (ORI code), not by census
geography, so there is no tract-level crime. The file already carries
``fips_state_county_code`` and ``fips_place_code``, though, which means no
separate LEAIC crosswalk is needed: agencies aggregate straight to county or
place, and those join to the camera table's ``geoid_county`` / ``geoid_place``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .dataverse import Identity, fetch_datafile

log = logging.getLogger(__name__)

UCR_GUESTBOOK_ID = 588
# Custom question ids on guestbook 588. 577 is a textarea and must be sent as
# a list of lines.
UCR_QUESTION_USE = 545
UCR_QUESTION_RESEARCH = 577
UCR_QUESTION_CITE = 572
UCR_TEXTAREA_IDS = frozenset({UCR_QUESTION_RESEARCH})
UCR_CITE_AGREE = "Yes, I agree to cite the data and acknowledge the source"

# Dataverse file ids for offenses_known_monthly_<year>.rds. The .rds files are
# ~8 MB against ~317 MB for the Stata equivalents, so they are strongly
# preferred; reading them needs `pyreadr`.
UCR_MONTHLY_RDS = {
    2019: 10899239,
    2020: 10899268,
    2021: 10899255,
    2022: 10899262,
    2023: 10899297,
}

# Index offences are the standard comparable aggregates; the file pre-computes
# them, so we do not re-derive and risk double-counting sub-categories.
CRIME_COLUMNS = [
    "actual_index_violent",
    "actual_index_property",
    "actual_index_total",
    "actual_murder",
    "actual_rape_total",
    "actual_robbery_total",
    "actual_assault_aggravated",
    "actual_burglary_total",
    "actual_theft_total",
    "actual_motor_vehicle_theft_total",
]

# Agencies whose jurisdiction is not a county subdivision. Rolling a state
# highway patrol into a county would double-count offences already reported by
# the local department covering the same ground.
LOCAL_AGENCY_TYPES = {
    "local police department",
    "sheriffs office",
    "constable/marshal",
}


def build_identity(name: str, email: str, institution: str,
                   research_question: str,
                   position: str = "Researcher",
                   use: str = "Academic paper") -> Identity:
    """Construct the guestbook Identity for the UCR archive.

    `research_question` is disclosed verbatim to Harvard Dataverse. Write it
    yourself -- it is a statement about your work, not boilerplate.
    """
    return Identity(
        name=name, email=email, institution=institution, position=position,
        answers=(
            (UCR_QUESTION_USE, use),
            (UCR_QUESTION_RESEARCH, research_question),
            (UCR_QUESTION_CITE, UCR_CITE_AGREE),
        ),
    )


def fetch_ucr_year(year: int, cache_dir: Path,
                   identity: Identity | None = None) -> pd.DataFrame:
    """Download and load one year of monthly agency-level UCR data."""
    try:
        import pyreadr
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Reading UCR .rds files needs pyreadr: pip install pyreadr"
        ) from exc

    if year not in UCR_MONTHLY_RDS:
        raise ValueError(
            f"No file id recorded for {year}; have {sorted(UCR_MONTHLY_RDS)}"
        )

    path = fetch_datafile(
        UCR_MONTHLY_RDS[year],
        Path(cache_dir) / f"ucr_offenses_known_monthly_{year}.rds",
        identity=identity,
        textarea_ids=UCR_TEXTAREA_IDS,
    )
    df = list(pyreadr.read_r(str(path)).values())[0]
    log.info("UCR %d: %d monthly agency rows", year, len(df))
    return df


def agency_year(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse monthly rows to one row per agency-year.

    Offences are summed across months; population is a per-agency constant so
    it is taken as a max rather than summed. `months_reported` is carried
    through because an agency that reported three months is not comparable to
    one that reported twelve -- filter on it before computing rates.
    """
    present = [c for c in CRIME_COLUMNS if c in df.columns]
    keys = ["ori", "year"]

    meta_cols = [c for c in ("agency_name", "state_abb", "agency_type",
                             "fips_state_code", "fips_county_code",
                             "fips_state_county_code", "fips_place_code")
                 if c in df.columns]

    agg = {c: "sum" for c in present}
    agg["population"] = "max"
    if "number_of_months_reported" in df.columns:
        agg["number_of_months_reported"] = "max"

    out = df.groupby(keys, as_index=False).agg(agg)
    meta = df.groupby(keys, as_index=False)[meta_cols].first()
    out = out.merge(meta, on=keys, how="left")

    out = out.rename(columns={"number_of_months_reported": "months_reported"})
    out["year"] = out["year"].astype("Int64")
    log.info("Collapsed to %d agency-year rows", len(out))
    return out


def crime_by_county(agency: pd.DataFrame, min_months: int = 12) -> pd.DataFrame:
    """Aggregate local agencies to county FIPS, with rates per 100k.

    Only local agencies are summed (see LOCAL_AGENCY_TYPES). Agencies reporting
    fewer than `min_months` months are dropped rather than annualized: a
    partial reporter's counts are not missing at random, and scaling them up
    invents precision the source does not have.
    """
    df = agency.copy()

    if "agency_type" in df.columns:
        before = len(df)
        df = df[df["agency_type"].isin(LOCAL_AGENCY_TYPES)]
        log.info("Kept %d/%d local agencies", len(df), before)

    if "months_reported" in df.columns:
        before = len(df)
        df = df[df["months_reported"] >= min_months]
        log.info("Kept %d/%d agencies reporting >= %d months",
                 len(df), before, min_months)

    df = df[df["fips_state_county_code"].notna()]
    df["geoid"] = df["fips_state_county_code"].astype(str).str.zfill(5)

    present = [c for c in CRIME_COLUMNS if c in df.columns]
    agg = {c: "sum" for c in present}
    agg["population"] = "sum"
    out = df.groupby("geoid", as_index=False).agg(agg)
    out = out.rename(columns={"population": "ucr_population"})
    out["ucr_agencies"] = df.groupby("geoid")["ori"].nunique().values

    pop = out["ucr_population"]
    for c in present:
        rate = c.replace("actual_", "") + "_per_100k"
        out[rate] = out[c].div(pop.where(pop > 0)) * 100_000

    log.info("Crime by county: %d counties, %d agencies rolled up",
             len(out), int(out["ucr_agencies"].sum()))
    return out


def crime_by_place(agency: pd.DataFrame, min_months: int = 12) -> pd.DataFrame:
    """Aggregate to census place FIPS (state+place, 7 chars).

    Place is the better match for a municipal `operator` name, but coverage is
    thinner than county: agencies with no place code (county sheriffs, most
    special jurisdictions) are excluded by construction.
    """
    df = agency.copy()
    if "months_reported" in df.columns:
        df = df[df["months_reported"] >= min_months]
    df = df[df["fips_place_code"].notna() & df["fips_state_code"].notna()]
    # Place GEOID is 2-char state + 5-char place.
    df["geoid"] = (df["fips_state_code"].astype(str).str.zfill(2)
                   + df["fips_place_code"].astype(str).str.zfill(5))

    present = [c for c in CRIME_COLUMNS if c in df.columns]
    agg = {c: "sum" for c in present}
    agg["population"] = "sum"
    out = df.groupby("geoid", as_index=False).agg(agg)
    out = out.rename(columns={"population": "ucr_population"})

    pop = out["ucr_population"]
    for c in present:
        out[c.replace("actual_", "") + "_per_100k"] = (
            out[c].div(pop.where(pop > 0)) * 100_000
        )

    log.info("Crime by place: %d places", len(out))
    return out
