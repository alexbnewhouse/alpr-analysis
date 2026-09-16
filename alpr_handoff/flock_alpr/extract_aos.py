"""Stage 3 - agency-level ALPR adoption records from EFF's Atlas of Surveillance.

The key output is ``ori9``: the FBI Originating Agency Identifier, which joins
exactly to UCR/NIBRS crime data. It is recoverable from the Atlas's
``NEWAOSNUMBER (ORI9)`` column on ~99% of Flock rows.
"""
import io
import re

import pandas as pd

from . import config, http

ORI_RE = re.compile(r"^[A-Z]{2}\d{7}$")
AS_OF_RE = re.compile(r"as of ([A-Z][a-z]+ \d{4}|\d{4})")
ALPR_TECH = "Automated License Plate Readers"

REQUIRED = {
    "NEWAOSNUMBER (ORI9)", "City", "County", "State", "Agency", "Type of LEA",
    "Summary", "Type of Juris", "Technology", "Vendor",
    "Link 1", "Link 1 Date", "Link 2", "Link 2 Date", "Link 3", "Link 3 Date",
}
DATE_COLS = ["Link 1 Date", "Link 2 Date", "Link 3 Date"]
OUT_COLS = [
    "ori9", "ori9_valid", "agency", "city", "county", "state", "lea_type",
    "juris_type", "vendor", "is_flock", "earliest_source_date",
    "summary_as_of_date", "source_urls",
]


def parse_ori(value):
    """Strip the technology suffix and validate. Returns (ori9|None, is_valid)."""
    v = (value or "").strip().upper()
    for suffix in ("ALPR", "DRON", "FACE", "BWC", "GUN", "RTCC"):
        if v.endswith(suffix):
            v = v[: -len(suffix)]
            break
    return (v, True) if ORI_RE.match(v) else (None, False)


def parse_aos(csv_bytes: bytes) -> pd.DataFrame:
    raw = pd.read_csv(
        io.BytesIO(csv_bytes), dtype=str, encoding="utf-8-sig", low_memory=False
    ).fillna("")

    missing = REQUIRED - set(raw.columns)
    if missing:
        raise ValueError(f"unexpected schema; missing columns: {sorted(missing)}")

    alpr = raw[raw["Technology"] == ALPR_TECH].copy()

    parsed = alpr["NEWAOSNUMBER (ORI9)"].map(parse_ori)
    alpr["ori9"] = [p[0] for p in parsed]
    alpr["ori9_valid"] = [p[1] for p in parsed]

    dates = alpr[DATE_COLS].apply(
        lambda c: pd.to_datetime(c, format="mixed", errors="coerce", utc=True)
    )
    alpr["earliest_source_date"] = dates.min(axis=1)

    alpr["summary_as_of_date"] = alpr["Summary"].str.extract(AS_OF_RE, expand=False)
    alpr["is_flock"] = alpr["Vendor"].str.contains("Flock", case=False, na=False)
    alpr["source_urls"] = alpr[["Link 1", "Link 2", "Link 3"]].apply(
        lambda r: "|".join(u for u in r if u), axis=1
    )

    out = alpr.rename(columns={
        "Agency": "agency", "City": "city", "County": "county", "State": "state",
        "Type of LEA": "lea_type", "Type of Juris": "juris_type", "Vendor": "vendor",
    })[OUT_COLS].reset_index(drop=True)
    out["ori9"] = out["ori9"].where(out["ori9_valid"], None)
    return out


def run(force=False) -> pd.DataFrame:
    df = parse_aos(http.fetch(config.AOS_CSV_URL, force=force))
    df.to_parquet(config.RAW / "aos_alpr_agencies.parquet", index=False)
    print(
        f"  {len(df)} ALPR rows | {int(df['is_flock'].sum())} Flock | "
        f"{100 * df['ori9_valid'].mean():.1f}% valid ORI | "
        f"{df['state'].nunique()} states"
    )
    return df
