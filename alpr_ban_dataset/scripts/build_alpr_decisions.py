"""Resolve municipal ALPR decisions to Census places and join the model frame.

    python external/build_alpr_decisions.py

The unit of observation is a MUNICIPAL DECISION -- a council vote, a manager's
signature, a referendum -- not a camera. The register deliberately holds
approvals as well as refusals: modelling who bans ALPRs requires knowing who
considered banning them and did not, and a file containing only bans cannot
supply that comparison.

Input : external/source/alpr_decisions.csv   (hand-maintained; schema below)
Output: external/data/alpr_decisions.parquet (resolved to place_geoid)

Two mechanical jobs are done here and nothing else: resolve each city to a
`place_geoid` so the register joins the model frames, and refuse to guess when
resolution is ambiguous. Coding decisions stay with the human.

SCHEMA
    city            municipality name as written in the source
    state           two-letter postal abbreviation
    place_geoid     manual override; filled when the resolver cannot decide
    action          see ACTIONS below
    decision_date   YYYY-MM[-DD] the body VOTED
    action_date     YYYY-MM[-DD] the decision took EFFECT (cameras off, code
                    amended). Often later than decision_date, sometimes by
                    months; survival models should use decision_date.
    adopted_date    YYYY-MM[-DD] the city first adopted ALPRs, where known.
                    With decision_date this gives a duration, which is what a
                    hazard model needs.
    body            city_council | mayor | city_manager | police_chief |
                    referendum | county_board | other
    vote_for        votes in favour, blank if not recorded
    vote_against    votes against, blank if not recorded
    reason          see REASONS below
    reversed        TRUE if the decision was later undone
    reversal_date   YYYY-MM[-DD] when it was undone
    source_type     ordinance | council_minutes | news | aggregator
    source_url      a link documenting the decision
    verified        TRUE only after a human has read the source
    notes           free text

Rows with verified=FALSE are carried through but counted separately. Nothing
sourced from an aggregator belongs in a regression before someone has read the
underlying document: the circulating lists disagree with one another, and
several entries conflate a council *discussion* with a council *vote*.
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from flock_alpr import config, geocode  # noqa: E402
from flock_alpr.place_police import _norm, PLACE_SUFFIX  # noqa: E402

SRC = HERE / "source" / "alpr_decisions.csv"
OUT = HERE / "data" / "alpr_decisions.parquet"

# The full decision space. Restrictive outcomes are listed first; `adopted`
# and `considered_no_action` are the comparison cases that make the others
# interpretable.
ACTIONS = {
    "ordinance_ban",        # codified prohibition
    "canceled",             # active termination of a live contract
    "suspended",            # pause or moratorium, program otherwise intact
    "not_renewed",          # contract allowed to lapse
    "declined_to_adopt",    # considered, voted against ever adopting
    "replaced_vendor",      # dropped Flock, kept ALPR
    "considered_no_action", # debated, tabled or took no vote
    "adopted",              # approved a contract or an expansion
}
REASONS = {
    "federal_immigration_access", "privacy", "unauthorized_access",
    "cost", "efficacy", "other", "",
}
BODIES = {
    "city_council", "mayor", "city_manager", "police_chief",
    "referendum", "county_board", "other", "",
}
COLS = ["city", "state", "place_geoid", "action", "decision_date", "action_date",
        "adopted_date", "body", "vote_for", "vote_against", "reason", "reversed",
        "reversal_date", "source_type", "source_url", "verified", "notes"]


def place_names() -> pd.DataFrame:
    """Every TIGER place with a normalised name, for matching."""
    import geopandas as gpd
    frames = []
    for st in config.STATES:
        fips = config.STATE_FIPS[st]
        p = geocode._cached_shapefile(
            f"{geocode.TIGER}/PLACE/tl_2024_{fips}_place.zip", f"place_{fips}.zip")
        g = gpd.read_file(f"zip://{p}", columns=["GEOID", "NAME", "geometry"])
        frames.append(pd.DataFrame({
            "place_geoid": g["GEOID"].astype(str).str.zfill(7),
            "name": g["NAME"], "state": st}))
    pl = pd.concat(frames, ignore_index=True)
    # TIGER carries a governmental suffix a news report never does
    # ("Nashville-Davidson metropolitan government (balance)").
    pl["key"] = _norm(pl["name"].str.replace(PLACE_SUFFIX, "", regex=True)) + "|" + pl["state"]
    return pl


def validate(df: pd.DataFrame) -> list:
    """Controlled vocabularies, checked loudly. A silent typo splits a category."""
    problems = []
    for col, allowed in (("action", ACTIONS), ("reason", REASONS), ("body", BODIES)):
        bad = sorted(set(df[col].str.strip()) - allowed)
        if bad:
            problems.append(f"{col}: unrecognised {bad}")
    for col in ("decision_date", "action_date", "adopted_date", "reversal_date"):
        s = df[col].str.strip()
        bad = s[(s != "") & ~s.str.match(r"^\d{4}-\d{2}(-\d{2})?$")]
        if len(bad):
            problems.append(f"{col}: not YYYY-MM[-DD] -> {sorted(set(bad))[:4]}")
    for col in ("vote_for", "vote_against"):
        s = df[col].str.strip()
        bad = s[(s != "") & ~s.str.match(r"^\d+$")]
        if len(bad):
            problems.append(f"{col}: not an integer -> {sorted(set(bad))[:4]}")
    return problems


def run():
    if not SRC.exists():
        raise SystemExit(f"no input at {SRC}; see the schema in this file's docstring")
    b = pd.read_csv(SRC, dtype=str).fillna("")
    for c in COLS:
        if c not in b.columns:
            b[c] = ""
    b = b[COLS]
    b["state"] = b["state"].str.strip().str.upper()

    for p in validate(b):
        print(f"  SCHEMA PROBLEM  {p}")

    b["key"] = _norm(b["city"]) + "|" + b["state"]
    pl = place_names()
    # A name can repeat within a state (a city and a CDP both called Mountain
    # View). Those are left for a human rather than assigned to the first hit.
    uniq = pl.drop_duplicates("key", keep=False).set_index("key")["place_geoid"]
    dupe = set(pl["key"]) - set(uniq.index)

    resolved = b["key"].map(uniq)
    # Zero-pad only a NON-EMPTY override: "".zfill(7) is "0000000", which is
    # seven characters long and would pass a naive length check as a real
    # GEOID, silently resolving every unmatched row to a place that does not
    # exist.
    manual = b["place_geoid"].str.strip()
    manual = manual.where(manual == "", manual.str.zfill(7))
    b["place_geoid"] = manual.where(manual.str.len() == 7, resolved)
    b["ambiguous"] = b["key"].isin(dupe) & b["place_geoid"].isna()

    bad = b[b["place_geoid"].isna() | (b["place_geoid"] == "")]
    ok = b[~b.index.isin(bad.index)].copy()
    ok["place_geoid"] = ok["place_geoid"].astype(str).str.zfill(7)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    ok.drop(columns=["key"]).to_parquet(OUT, index=False)

    ver = ok["verified"].str.upper().eq("TRUE")
    print(f"  rows                : {len(b):,}")
    print(f"  resolved to a place : {len(ok):,}")
    print(f"  verified by a human : {ver.sum():,}  ({len(ok) - ver.sum():,} still to check)")
    print(f"  with a source_url   : {(ok['source_url'].str.strip() != '').sum():,}")
    print(f"  with a vote tally   : {(ok['vote_for'].str.strip() != '').sum():,}")
    print(f"  with decision_date  : {(ok['decision_date'].str.strip() != '').sum():,}")
    if len(bad):
        print(f"  UNRESOLVED ({len(bad)}) -- set place_geoid by hand:")
        for _, r in bad.iterrows():
            why = "name repeats in state" if r["ambiguous"] else "no TIGER match"
            print(f"    {r['city']}, {r['state']}  ({why})")
    print(f"\n  by action: {ok['action'].value_counts().to_dict()}")
    print(f"  -> {OUT}")


if __name__ == "__main__":
    run()
