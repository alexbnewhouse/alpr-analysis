# ALPR pause / ban dataset — package contents

Everything here concerns **one question only**: which municipalities and
counties paused, cancelled or banned ALPRs, and what predicts it. Nothing here
concerns the adoption or intensity models.

**Start with `HANDOFF_ban_dataset.md`.** It explains the sources, the search
strategy, the schema, what has been established, and what remains. This file
just says where things are.

---

## What's in the box

```
HANDOFF_ban_dataset.md      read this first
register/
  alpr_decisions_merged.csv      THE REGISTER -- 151 places, this is the file to edit
  alpr_decisions_counties.csv    28 county-level decisions, no place_geoid
  alpr_decisions.csv             early 13-row hand seed, superseded, kept for history
sources/
  nexis/
    nexis_candidates.csv         parser output, 907 rows, one per article
    *.DOCX                       the raw Nexis Uni exports
  deflock/
    deflock_flockwins.json       DeFlock CMS snapshot, 153 records
scripts/
  parse_nexis.py                 .docx -> candidate rows
  merge_decision_sources.py      Nexis + DeFlock -> register
  build_alpr_decisions.py        city/state -> place_geoid
  table_decision_descriptives.R  summary statistics table
  test_alpr_decisions.py         6 network-free tests
docs/
  table_decision_descriptives.tex
```

Paths inside the handoff refer to their locations in the main repository
(`external/source/...`, `external/...`, `docs/...`). Here they are grouped by
purpose instead. The mapping is:

| handoff path | here |
|---|---|
| `external/source/alpr_decisions*.csv` | `register/` |
| `external/source/nexis/` | `sources/nexis/` |
| `external/source/deflock/` | `sources/deflock/` |
| `external/*.py`, `external/*.R` | `scripts/` |

---

## What you can do without the repository

**Verification, which is the blocking task.** Open
`register/alpr_decisions_merged.csv` in Excel, R or anything else. To check a
row, use its `source_url` (present for 134 of 151), or find the article in
`sources/nexis/nexis_candidates.csv`, which carries the `headline`,
`publication` and `pub_date` for every Nexis-derived row. The full article text
is in the corresponding `.DOCX`.

Set `verified` to `TRUE` once you have read the source, and correct `action`,
`state` and the vote tallies as needed. The handoff explains the suggested
order of work and the known failure modes — the `state` column in particular is
wrong more often than the city.

## What needs the full repository

The scripts import the `flock_alpr` package and read data that is not included
here:

- all three Python scripts import `flock_alpr.config`, `flock_alpr.geocode`
  and `flock_alpr.place_police`
- `parse_nexis.py` needs `external/data/model_frame_place.parquet` and
  downloads TIGER place shapefiles on first run, caching them under
  `data/raw/cache/`

So the scripts are here **for reference and review**, to show exactly how each
column was produced. To actually re-run the pipeline, work in a clone of the
repository rather than in this folder.

---

## Before you start editing

The register is a hand-edited CSV with no locking. If two people verify rows in
separate copies, reconciling them is painful. Agree first on **who owns the
file**, or split the work so edits cannot collide — by state, or by source, or
by one person owning it outright.

`merge_decision_sources.py` is written to protect that work: re-running it
preserves any row marked `verified=TRUE` exactly as edited, and refreshes only
the provenance columns.

---

## One caveat worth repeating

**No row in the register has been verified against its source yet.** Roughly a
quarter of the news-derived entries are expected to be false positives on
review. Nothing here should go into a regression before that pass is done.
