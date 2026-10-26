#!/usr/bin/env python
"""Merge the source-verification pass into a clean ALPR pause/ban register.

The 2026-10-26 pass re-read every row of Stone's register
(alpr_ban_dataset/register/alpr_decisions_merged.csv, 151 places, and
alpr_decisions_counties.csv, 28 counties) against its source, corrected the
jurisdiction where the Nexis parser had attached the wrong one, coded action,
permanence, date, body, vote and reason, and added decisions missing from both
sources up to the 2026-09-30 cutoff. The pass's raw outputs live in
alpr_ban_dataset/verification/ (one CSV per batch, one row per input row).

This script
  1. stacks the batch outputs, validates every controlled vocabulary,
  2. resolves each jurisdiction to a place GEOID (7) or county FIPS (5) against
     the 2023 Census cartographic boundary files, refusing to guess on ties,
  3. drops non-decisions and duplicates, applies the cutoff, and
  4. codes the draft's three outcomes: pause, ban, any restriction.

Run from the repo root:
  ~/flock_research/.venv/bin/python scripts/04_build_bans_register.py [verification_dir]

Outputs
  alpr_ban_dataset/register/alpr_decisions_verified.csv   every row, with status + evidence (the audit trail)
  data/bans/bans_quick.csv                                in-scope decisions only (Notion deliverable; Finding Flock vocabulary)
  data/bans/place_decisions.csv                           one row per place GEOID with dv_pause / dv_ban / dv_any
  data/bans/county_decisions.csv                          one row per county FIPS, same
  data/bans/build_report.md                               counts, unresolved names, dropped rows
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

VERIFY = Path(sys.argv[1] if len(sys.argv) > 1 else "alpr_ban_dataset/verification")
CACHE = Path.home() / "flock_research/alpr_pipeline/data/cache"
CUTOFF = "2026-09-30"
COUSUB_ZIP = Path("data/raw/tiger/cb_2023_us_cousub_500k.zip")  # www2.census.gov/geo/tiger/GENZ2023/shp/
OUT_REG = Path("alpr_ban_dataset/register/alpr_decisions_verified.csv")
OUT_DIR = Path("data/bans")

COLS = ["row_id", "status", "corrected_city", "corrected_state", "level", "action", "permanence",
        "decision_date", "action_date", "body", "vote_for", "vote_against", "reason", "reason_secondary",
        "vendor", "reversed", "reversal_date", "evidence_url", "evidence_quote", "confidence", "notes"]
VOCAB = {
    "status": {"confirmed", "not_a_decision", "duplicate", "unconfirmed"},
    "level": {"place", "county", "other"},
    "action": {"ordinance_ban", "canceled", "suspended", "not_renewed", "declined_to_adopt",
               "replaced_vendor", "considered_no_action", "adopted"},
    "permanence": {"temporary", "permanent", "unclear"},
    "body": {"city_council", "mayor", "city_manager", "police_chief", "referendum", "county_board", "sheriff", "other"},
    "reason": {"federal_immigration_access", "privacy", "unauthorized_access", "cost", "efficacy", "other"},
    "confidence": {"high", "medium", "low"},
}
# The draft's three outcomes. Cancelling Flock and switching vendor is still a
# Flock cancellation -- the draft frames the backlash as Flock-specific.
PAUSE = {"suspended"}
BAN = {"canceled", "not_renewed", "ordinance_ban", "replaced_vendor"}
ANY = PAUSE | BAN | {"declined_to_adopt"}
FF = {"canceled": "canceled", "not_renewed": "non-renewal", "suspended": "paused",
      "declined_to_adopt": "rejected", "ordinance_ban": "banned", "replaced_vendor": "canceled"}


def md(x: pd.Series | pd.DataFrame) -> str:
    """Markdown table without the optional tabulate dependency."""
    d = x.to_frame() if isinstance(x, pd.Series) else x
    d = d.reset_index()
    rows = [" | ".join(map(str, d.columns)), " | ".join("---" for _ in d.columns)]
    rows += [" | ".join(map(str, r)) for r in d.itertuples(index=False)]
    return "\n".join(f"| {r} |" for r in rows)


def clean(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip()


def load(pattern: str) -> pd.DataFrame:
    frames = []
    for f in sorted(VERIFY.glob(pattern)):
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
        missing = set(COLS) - set(d.columns)
        if missing:
            raise SystemExit(f"{f.name}: missing columns {sorted(missing)}")
        frames.append(d[COLS].assign(batch=f.stem))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS + ["batch"])


# ---- 1. stack + validate ----------------------------------------------------------
inp = pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False) for f in sorted(VERIFY.glob("in_*.csv"))])
out = load("out_*.csv")
gap = load("gap_*.csv")
gap["status"] = gap.status.replace("", "confirmed")
problems = []
lost = set(inp.row_id) - set(out.row_id)
if lost:
    problems.append(f"{len(lost)} input rows have no verification row: {sorted(lost)[:10]}")
dup_ids = out.row_id[out.row_id.duplicated()].tolist()
if dup_ids:
    problems.append(f"verification rows repeated: {dup_ids[:10]} (kept first)")
    out = out.drop_duplicates("row_id")
orig = inp.set_index("row_id")[["city", "state", "action", "decision_date", "sources", "source_url"]].add_prefix("orig_")
out = out.join(orig, on="row_id")
out["origin"] = "register"
gap["origin"] = "new_" + gap.batch.str.replace("gap_", "", regex=False)
reg = pd.concat([out, gap], ignore_index=True)
for c in COLS:
    reg[c] = clean(reg[c])
for c in ("status", "level", "action", "permanence", "body", "reason", "reason_secondary", "confidence"):
    reg[c] = reg[c].str.lower()
for c, ok in VOCAB.items():
    bad = reg[(reg[c] != "") & ~reg[c].isin(ok)]
    for _, r in bad.iterrows():
        problems.append(f"{r.row_id}: {c}={r[c]!r} not in vocabulary -> blank")
    reg.loc[bad.index, c] = ""
bad = reg[(reg.reason_secondary != "") & ~reg.reason_secondary.isin(VOCAB["reason"])]
reg.loc[bad.index, "reason_secondary"] = ""
reg["corrected_state"] = reg.corrected_state.str.upper()
reg["decision_date"] = reg.decision_date.str.extract(r"^(\d{4}-\d{2}(?:-\d{2})?)", expand=False).fillna("")
reg["decision_month"] = reg.decision_date.str[:7]

# ---- 2. resolve jurisdictions -----------------------------------------------------
pl = gpd.read_file(f"zip://{CACHE / 'cb_2023_us_place_500k.zip'}", ignore_geometry=True)
co = gpd.read_file(f"zip://{CACHE / 'cb_2023_us_county_500k.zip'}", ignore_geometry=True)


def norm(name: str) -> str:
    s = name.lower().replace("st.", "saint").replace("ste.", "sainte").replace("’", "'")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"^(city|town|village|borough|township|municipality) of ", "", s)
    s = re.sub(r"\b(city|town|village|borough|township|cdp|municipality|charter|consolidated government|"
               r"metropolitan government|unified government|urban county|metro government)\b", " ", s)
    s = re.sub(r"\b(balance)\b", " ", s)
    return re.sub(r"[^a-z0-9']+", " ", s).strip()


pl["key"] = pl.NAME.map(norm)
pl_idx = pl.groupby(["STUSPS", "key"]).GEOID.agg(list).to_dict()
incorporated = set(pl.GEOID[pl.LSAD != "57"])
cities = set(pl.GEOID[pl.LSAD == "25"])
cs = gpd.read_file(f"zip://{COUSUB_ZIP}", ignore_geometry=True)
cs = cs[~cs.LSAD.isin(["00", "22", "23", "46"])]  # drop CCDs, census subareas, unorganized territory
cs["key"] = cs.NAME.map(norm)
cs_idx = cs.groupby(["STUSPS", "key"]).GEOID.agg(list).to_dict()
co["key"] = co.NAMELSAD.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()
co["key2"] = co.NAME.str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.strip()
co_idx = {**co.groupby(["STUSPS", "key2"]).GEOID.agg(list).to_dict(), **co.groupby(["STUSPS", "key"]).GEOID.agg(list).to_dict()}
# Consolidated city-counties and independent cities decide as one body; a
# county-level row naming one of these resolves to the place.
manual = {("TN", "nashville"): "4752006", ("KY", "louisville"): "2148006", ("IN", "indianapolis"): "1836003",
          ("GA", "athens"): "1303440", ("GA", "augusta"): "1304204", ("CO", "denver"): "0820000",
          ("CA", "san francisco"): "0667000", ("KS", "kansas city"): "2036000"}


ALIAS = {("MA", "North Attleboro"): "North Attleborough"}
CONSOLIDATED = {("FL", "duval county"): "1235000", ("TN", "davidson county"): "4752006",
                ("IN", "marion county"): "1836003", ("KY", "jefferson county"): "2148006",
                ("GA", "clarke county"): "1303440", ("GA", "richmond county"): "1304204",
                ("CO", "denver county"): "0820000", ("CA", "san francisco county"): "0667000",
                ("KS", "wyandotte county"): "2036000"}


def resolve(r) -> tuple[str, str, str]:
    """-> (geoid, geo_type, problem). geo_type: place | cousub | county."""
    st, name = r.corrected_state, r.corrected_city
    name = ALIAS.get((st, name), name)
    if r.level == "county":
        if (st, name.lower()) in CONSOLIDATED:  # one government; count it once, as the city
            return CONSOLIDATED[(st, name.lower())], "place", ""
        k = re.sub(r"[^a-z0-9 ]", "", name.lower().replace("st.", "st")).strip()
        hits = co_idx.get((st, k)) or co_idx.get((st, k + " county")) or co_idx.get((st, k.replace(" county", "")))
        if hits and len(set(hits)) == 1:
            return hits[0], "county", ""
        return "", "", "ambiguous" if hits else "no_match"
    if r.level == "place":
        k = norm(name)
        if (st, k) in manual:
            return manual[(st, k)], "place", ""
        hits = sorted(set(pl_idx.get((st, k), [])))
        if len(hits) > 1:  # El Cerrito city vs El Cerrito CDP: councils sit in incorporated places
            hits = [g for g in hits if g in incorporated] or hits
        if len(hits) > 1:  # Waukesha city vs Waukesha village: prefer the city
            hits = [g for g in hits if g in cities] or hits
        if len(hits) == 1:
            return hits[0], "place", ""
        if hits:
            return "", "", "ambiguous"
        # New England towns and MI/OH/NJ/PA townships are county subdivisions,
        # not Census places; they decide, but sit outside the place universe.
        hits = sorted(set(cs_idx.get((st, k), [])))
        if len(hits) == 1:
            return hits[0], "cousub", ""
        return "", "", "ambiguous_cousub" if hits else "no_match"
    return "", "", "not_place_or_county"


res = reg.apply(resolve, axis=1, result_type="expand")
reg["geoid"], reg["geo_type"], reg["geoid_problem"] = res[0], res[1], res[2]

# ---- 3. scope ---------------------------------------------------------------------
reg["in_scope"] = (
    reg.status.eq("confirmed")
    & reg.action.isin(ANY)
    & reg.level.isin(["place", "county"])
    & reg.geoid.ne("")
    & (reg.decision_date.eq("") | reg.decision_date.le(CUTOFF + "~"))
)
reg["after_cutoff"] = reg.decision_date.gt(CUTOFF + "~") & reg.decision_date.ne("")
# The same decision reported twice (register + a gap search, or two gap searches
# covering the same state): same jurisdiction, same outcome category, dated within
# 45 days of each other (or one undated). Keep the best-evidenced report. A pause
# followed weeks later by a cancellation stays as two decisions.
reg["category"] = reg.action.map(lambda a: "pause" if a in PAUSE else "ban" if a in BAN
                                 else "rejected" if a == "declined_to_adopt" else "")
reg["_date"] = pd.to_datetime(reg.decision_date.where(reg.decision_date.str.len() == 10,
                                                      reg.decision_date + "-15"), errors="coerce")
reg["_r"] = (reg.confidence.map({"high": 0, "medium": 1, "low": 2}).fillna(3)
             + reg.origin.ne("register") * 0.5)  # ties go to the original register row
reg = reg.sort_values(["_r", "row_id"])
reg["dup_of"] = ""
for _, grp in reg[reg.in_scope].groupby(["geo_type", "geoid", "category"]):
    kept: list = []
    for i, r in grp.iterrows():
        match = next((k for k in kept if pd.isna(r._date) or pd.isna(reg.at[k, "_date"])
                      or abs((r._date - reg.at[k, "_date"]).days) <= 45), None)
        if match is None:
            kept.append(i)
        else:
            reg.at[i, "dup_of"] = reg.at[match, "row_id"]
dupe = reg.dup_of.ne("")
reg.loc[dupe, "in_scope"] = False
reg.loc[dupe, "status"] = reg.loc[dupe, "status"] + "|dedup"
reg = reg.drop(columns=["_date", "_r"])
# Decisions that followed a state action rather than a local initiative: Florida
# DOT revoking ALPR permits on state roads (Aug 31, 2026), the Texas governor's
# pause of state grant funding (Aug-Sep 2026), and Washington's SB 6002 (2026).
# Flagged from the verifier's notes/quote; the models are re-run without them.
STATE_TRIGGER = {"FL": r"fdot|department of transportation|dot permit|state-road order|state road",
                 "TX": r"abbott|state funding|state grant|funding pause|funding freeze|grant pause|mvcpa",
                 "WA": r"sb 6002"}
# Mentions of a state trigger that are not one: the pause predates SB 6002 and
# the law is cited only for the later reactivation.
# Renton (P132) is coded as the council's own vote, not the earlier police compliance pause.
NOT_STATE_TRIGGERED = {"P124", "P133", "P135", "P132"}
txt = (reg.notes + " " + reg.evidence_quote).str.lower()
reg["state_triggered"] = [
    int(bool(STATE_TRIGGER.get(st)) and bool(re.search(STATE_TRIGGER[st], t)) and rid not in NOT_STATE_TRIGGERED)
    for st, t, rid in zip(reg.corrected_state, txt, reg.row_id)]
reg = reg.sort_values(["level", "corrected_state", "corrected_city", "decision_date"])
reg["dv_pause"] = reg.action.isin(PAUSE).astype(int)
reg["dv_ban"] = reg.action.isin(BAN).astype(int)
reg["dv_any"] = reg.action.isin(ANY).astype(int)
OUT_REG.parent.mkdir(parents=True, exist_ok=True)
reg.to_csv(OUT_REG, index=False)

# ---- 4. outputs -------------------------------------------------------------------
OUT_DIR.mkdir(parents=True, exist_ok=True)
s = reg[reg.in_scope].copy()
# invariants: every in-scope row has a GEOID of the right width for its type, and
# no decision after the cutoff slipped through
width = s.geo_type.map({"place": 7, "cousub": 10, "county": 5})
assert (s.geoid.str.len() == width).all(), s[s.geoid.str.len() != width][["row_id", "geoid", "geo_type"]]
assert not s.decision_date.gt(CUTOFF + "~").any()
assert s.status.eq("confirmed").all()
s["dv_any_local"] = s.dv_any * (1 - s.state_triggered)
quick = s.assign(place=s.corrected_city, state=s.corrected_state, action_ff=s.action.map(FF),
                 trigger=s.reason, source=s.evidence_url)
quick[["level", "geo_type", "geoid", "place", "state", "decision_date", "action", "action_ff", "permanence", "state_triggered", "body",
       "vote_for", "vote_against", "trigger", "reason_secondary", "vendor", "reversed", "confidence",
       "origin", "source"]].to_csv(OUT_DIR / "bans_quick.csv", index=False)


def per_unit(geo_type: str, col: str) -> pd.DataFrame:
    d = s[s.geo_type == geo_type]
    g = d.groupby("geoid").agg(
        dv_pause=("dv_pause", "max"), dv_ban=("dv_ban", "max"), dv_any=("dv_any", "max"),
        dv_any_local=("dv_any_local", "max"),
        n_decisions=("action", "size"),
        first_decision=("decision_date", lambda x: min([v for v in x if v], default="")),
        actions=("action", lambda x: ";".join(sorted(set(x)))),
        reasons=("reason", lambda x: ";".join(sorted(set(v for v in x if v)))))
    g.index.name = col
    return g.reset_index()


per_unit("place", "place_geoid").to_csv(OUT_DIR / "place_decisions.csv", index=False)
per_unit("cousub", "cousub_geoid").to_csv(OUT_DIR / "cousub_decisions.csv", index=False)
per_unit("county", "county_fips").to_csv(OUT_DIR / "county_decisions.csv", index=False)

orig_rows = reg[reg.origin == "register"]
conf_orig = orig_rows[orig_rows.status.str.startswith("confirmed")]
juris_fixed = ((conf_orig.orig_city.str.replace(r",\s*[A-Z]{2}$", "", regex=True).str.lower().str.strip()
                != conf_orig.corrected_city.str.lower().str.strip())
               | (conf_orig.corrected_state != conf_orig.orig_state))
lines = [
    "# Ban/pause register build report", "",
    f"Verification dir: `{VERIFY}` · cutoff {CUTOFF}", "",
    "## Verification of the existing register", "",
    md(orig_rows.status.value_counts().to_frame("rows")), "",
    f"Confirmed rows whose jurisdiction was wrong (city or state changed): {int(juris_fixed.sum())}",
    f"Confirmed rows whose action was recoded: {int((conf_orig.action != conf_orig.orig_action).sum())}", "",
    "## New decisions from the gap search", "",
    md(reg[reg.origin != "register"].groupby("origin").status.value_counts().to_frame("rows")), "",
    "## In scope", "",
    md(s.groupby(["geo_type", "action"]).size().to_frame("decisions")), "",
    f"Duplicate reports collapsed: {int(reg.dup_of.ne('').sum())}",
    f"State-triggered (FL DOT / TX funding pause / WA SB 6002): "
    + ", ".join(f"{k} {v}" for k, v in s[s.state_triggered == 1].groupby("corrected_state").size().items()),
    "Unique jurisdictions: " + " · ".join(f"{k} {v}" for k, v in s.groupby("geo_type").geoid.nunique().items()),
    f"Confirmed decisions dated after the cutoff (excluded): {int((reg.status.eq('confirmed') & reg.after_cutoff).sum())}",
    f"Confirmed, level=other (state agency, university, ...; excluded): {int((reg.status.eq('confirmed') & reg.level.eq('other')).sum())}", "",
    "## Unresolved jurisdictions (confirmed rows, no GEOID)", "",
]
unres = reg[reg.status.eq("confirmed") & reg.level.isin(["place", "county"]) & reg.geoid.eq("")]
lines += [f"- {r.row_id}: {r.corrected_city}, {r.corrected_state} ({r.level}) -- {r.geoid_problem}" for _, r in unres.iterrows()] or ["- none"]
lines += ["", "## Validation problems", ""] + ([f"- {p}" for p in problems] or ["- none"])
(OUT_DIR / "build_report.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
