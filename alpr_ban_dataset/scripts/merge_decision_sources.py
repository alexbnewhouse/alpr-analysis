"""Merge every source of municipal ALPR decisions into one register.

    python external/merge_decision_sources.py

Sources, all independently constructed and all incomplete:

  deflock  external/source/deflock/deflock_flockwins.json
           The DeFlock project's "wins" list, pulled from its CMS
           (https://cms.deflock.me/items/flockWins). Activist-maintained,
           reaches small municipalities the press never covered.
  nexis    external/source/nexis/nexis_candidates.csv
           Our Nexis Uni pull, parsed by parse_nexis.py. Reaches cities that
           got newspaper coverage, which skews larger.

They overlap on only 15 places out of 151. The overlap is size-graded --
median population 61k in both sources, 34k in Nexis alone, 18k in DeFlock
alone -- which is the coverage bias the two collection methods imply. Using
either source alone would lose most of the universe, so the register is their
union and every row records which sources support it.

IDEMPOTENCE. Re-running never overwrites human work: any row already marked
verified=TRUE is preserved exactly as edited, and only its `sources` field is
refreshed. Delete the output file to rebuild from scratch.

Writes:
  external/source/alpr_decisions_merged.csv   places, ready to verify
  external/source/alpr_decisions_counties.csv counties, which have no
                                              place_geoid and cannot join the
                                              place frame; kept so a
                                              county-level extension is
                                              possible later.
"""
import csv
import json
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from flock_alpr.place_police import _norm            # noqa: E402
from parse_nexis import place_lookup                 # noqa: E402
from build_alpr_decisions import COLS                # noqa: E402

DEFLOCK = HERE / "source" / "deflock" / "deflock_flockwins.json"
NEXIS = HERE / "source" / "nexis" / "nexis_candidates.csv"
OUT = HERE / "source" / "alpr_decisions_merged.csv"
OUT_CO = HERE / "source" / "alpr_decisions_counties.csv"

# DeFlock's vocabulary is coarser than ours. "Cameras Deactivated" does not
# distinguish a pause from a permanent end, so it maps to `canceled` and is
# flagged in notes -- the suspended/canceled split has to be made by reading
# the source, which is exactly what the verification pass is for.
OUTCOME_MAP = {
    "Contract Canceled": "canceled",
    "Cameras Deactivated": "canceled",
    "Contract Rejected": "declined_to_adopt",
    "ALPRs Banned": "ordinance_ban",
    "Contract Reinstated": "canceled",      # reversed=TRUE set below
}
MONTHS = {m: f"{i+1:02d}" for i, m in enumerate(
 ["January","February","March","April","May","June","July","August",
  "September","October","November","December"])}
RESTRICTIVE = {"canceled", "suspended", "not_renewed", "declined_to_adopt",
               "ordinance_ban"}


def resolver():
    pl = place_lookup()
    pl["key"] = pl["norm"] + "|" + pl["state"]
    # A name repeating within a state is ambiguous and is left unresolved.
    return pl.drop_duplicates("key", keep=False).set_index("key")["place_geoid"]


def from_deflock(uniq):
    if not DEFLOCK.exists():
        return pd.DataFrame(), pd.DataFrame()
    rows = json.load(open(DEFLOCK))["data"]
    d = pd.DataFrame(rows)
    d["is_county"] = d["cityState"].str.contains("County|Parish", case=False, na=False)
    d["city"] = d["cityState"].str.rsplit(",", n=1).str[0].str.strip()
    d["state"] = d["cityState"].str.rsplit(",", n=1).str[1].str.strip().str.upper()
    mo = d["monthYear"].str.extract(r"(\w+)\s+(\d{4})")
    d["decision_date"] = mo[1] + "-" + mo[0].map(MONTHS)
    d["decision_date"] = d["decision_date"].fillna("")
    # The source link lives inside the description HTML.
    d["source_url"] = d["description"].str.extract(r'href="([^"]+)"')[0].fillna("")
    d["notes"] = (d["description"].str.replace(r"<[^>]+>", " ", regex=True)
                  .str.replace(r"\s+", " ", regex=True).str.strip().str[:280])
    d["action"] = d["outcome"].map(OUTCOME_MAP).fillna("canceled")
    d["reversed"] = (d["outcome"] == "Contract Reinstated").map({True: "TRUE", False: ""})
    d["place_geoid"] = (_norm(d["city"]) + "|" + d["state"]).map(uniq).fillna("")
    d["source_type"] = "aggregator"
    d["src"] = "deflock"
    return d[~d.is_county], d[d.is_county]


def from_nexis(uniq):
    if not NEXIS.exists():
        return pd.DataFrame()
    n = pd.read_csv(NEXIS, dtype=str).fillna("")
    n = n[(n["drop_reason"] == "") & (n["duplicate"].str.upper() == "FALSE")]
    n = n[n["action"].isin(RESTRICTIVE) & n["city_conf"].isin(["high", "medium"])]
    # Keep the best-evidenced row per place: highest confidence, then earliest
    # date, so the register carries the decision rather than a later re-report.
    n["rank"] = n["city_conf"].map({"high": 0, "medium": 1})
    n = n.sort_values(["rank", "pub_date"]).drop_duplicates("place_geoid")
    n["decision_date"] = n["pub_date"].str[:7]
    n["source_type"] = "news"
    n["src"] = "nexis"
    n["reversed"] = ""
    return n


def merge(frames):
    """Union on place_geoid; record which sources support each row."""
    keep = ["city", "state", "place_geoid", "action", "decision_date",
            "source_type", "source_url", "notes", "reversed", "vote_for",
            "vote_against", "src"]
    parts = []
    for f in frames:
        if not len(f):
            continue
        g = f.copy()
        for c in keep:
            if c not in g.columns:
                g[c] = ""
        parts.append(g[keep])
    allrows = pd.concat(parts, ignore_index=True)
    allrows = allrows[allrows["place_geoid"].astype(str).str.len() == 7]

    out = []
    for gid, grp in allrows.groupby("place_geoid"):
        srcs = sorted(set(grp["src"]))
        # Prefer the row carrying a source URL, then the earliest date: the
        # first report of a decision is the decision.
        grp = grp.assign(_has=grp["source_url"].ne("").astype(int))
        best = grp.sort_values(["_has", "decision_date"],
                               ascending=[False, True]).iloc[0]
        r = {c: "" for c in COLS}
        r.update({c: best[c] for c in COLS if c in best.index})
        r["place_geoid"] = gid
        r["sources"] = "+".join(srcs)
        r["n_sources"] = str(len(srcs))
        # Disagreement between sources is exactly what a verifier should look
        # at first, so surface it rather than silently taking one.
        acts = sorted(set(grp["action"]))
        r["source_conflict"] = "TRUE" if len(acts) > 1 else ""
        if len(acts) > 1:
            r["notes"] = f"[sources disagree: {', '.join(acts)}] " + str(r.get("notes", ""))[:220]
        r["verified"] = "FALSE"
        out.append(r)
    return pd.DataFrame(out)


def run():
    uniq = resolver()
    dfp, dfc = from_deflock(uniq)
    nx = from_nexis(uniq)
    merged = merge([dfp, nx])

    cols = COLS + ["sources", "n_sources", "source_conflict"]
    merged = merged.reindex(columns=cols).fillna("")

    # Preserve human work: verified rows survive a rebuild untouched except
    # for their provenance fields.
    if OUT.exists():
        prev = pd.read_csv(OUT, dtype=str).fillna("")
        done = prev[prev["verified"].str.upper() == "TRUE"]
        if len(done):
            fresh = merged.set_index("place_geoid")
            for _, row in done.iterrows():
                gid = row["place_geoid"]
                if gid in fresh.index:
                    for c in ("sources", "n_sources", "source_conflict"):
                        row[c] = fresh.loc[gid, c]
            merged = pd.concat(
                [done, merged[~merged["place_geoid"].isin(done["place_geoid"])]],
                ignore_index=True)
            print(f"  preserved {len(done)} verified rows")

    merged.sort_values(["state", "city"]).to_csv(OUT, index=False, quoting=csv.QUOTE_MINIMAL)
    if len(dfc):
        dfc[["cityState", "decision_date", "action", "source_url", "notes"]].to_csv(
            OUT_CO, index=False)

    v = merged["sources"].value_counts()
    print(f"  DeFlock places   : {len(dfp):3d}  ({len(dfc)} counties held separately)")
    print(f"  Nexis places     : {len(nx):3d}")
    print(f"  MERGED register  : {len(merged):3d} places")
    for k in ("deflock+nexis", "deflock", "nexis"):
        if k in v:
            print(f"      {k:16s} {v[k]:3d}")
    print(f"  source conflicts : {(merged['source_conflict'] == 'TRUE').sum()}")
    print(f"  with source_url  : {(merged['source_url'] != '').sum()}")
    print(f"  with decision date: {(merged['decision_date'] != '').sum()}")
    print(f"  verified         : {(merged['verified'].str.upper() == 'TRUE').sum()}")
    print(f"\n  -> {OUT}")


if __name__ == "__main__":
    run()
