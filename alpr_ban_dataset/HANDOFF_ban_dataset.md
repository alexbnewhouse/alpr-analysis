# Handoff: the ALPR pause / ban dataset

Scope: **only** the dataset of municipalities and counties that paused,
cancelled or banned ALPRs. Nothing here concerns the adoption or intensity
models. For those, see `HANDOFF.md` and `CLAUDE.md`.

---

## 1. What this is

A register of **municipal decisions** — a council vote, a manager's signature,
a referendum — to suspend, decline to renew, or prohibit ALPR technology. The
unit is the decision, not the camera.

The register deliberately holds **approvals as well as refusals**. Modelling
who bans ALPRs requires knowing who considered banning them and did not; a file
containing only bans supplies no comparison group.

**Why this is a separate question from adoption.** Adoption is a procurement
decision — a chief signs a subscription, often below the competitive-bidding
threshold, with no public vote. A ban is a legislative act by an elected body.
Different actor, different process. Empirically the two behave very differently:
partisanship is null for adoption at every geographic level and across three
independent measures, but cities in the register average **37.8% Trump 2020
vote against 51.4% among all adopting places**.

---

## 2. State as of this handoff

| | |
|---|---|
| places in the register | **151** (150 join the place model frame) |
| counties, held separately | **28** |
| **verified against source** | **0** |
| rows with a source URL | 134 |
| rows with a decision date | 119 |
| rows where the two sources disagree | 6 |

By provenance: DeFlock only **95**, Nexis only **41**, both **15**.

By action: canceled 103, declined\_to\_adopt 28, suspended 16, not\_renewed 2,
ordinance\_ban 2.

> **The register is not ready for a regression.** No row has been confirmed
> against its underlying document, and roughly a quarter of the news-derived
> entries are expected to be false positives on manual review.

---

## 3. Sources

Two, independently constructed, with different selection mechanisms. **Neither
is close to complete on its own**, which is the main reason both are used.

### 3a. Nexis Uni (local news)

Institutional subscription; cannot be reached programmatically. Exports are
`.docx`, saved to `external/source/nexis/`.

**Settings, identical for every search.** Content type News, then Publication
Type limited to Newspapers, Web-based Publications, Newswires & Press Releases,
and Broadcast Transcripts. Group duplicates on. Sort by date. Download as
**Full documents**, **MS Word (docx)**, **grouped into a single file**, max 500
per delivery.

**The searches, in the order they were run.**

*Step 1 — calibration, to settle coding rules on a small high-confidence set:*
```
HLEAD(("license plate reader" OR ALPR OR "Flock Safety") AND (ban OR banned OR moratorium OR cancel! OR terminat! OR suspend! OR "not renew"))
```

*Step 2 — codified bans (revised; see pitfalls):*
```
("license plate reader" OR ALPR OR "Flock Safety" OR "plate reader") W/25 (ordinance OR moratorium OR "municipal code" OR "city code" OR "voted to prohibit" OR "prohibiting the use" OR repeal!) AND NOT (RCMP OR Ontario OR Guelph OR "prohibited driver")
```

*Step 3 — the main restrictive query, run once per year slice:*
```
("license plate reader" OR "license plate readers" OR "license plate recognition" OR "automated license plate" OR "automatic license plate" OR ALPR OR "plate reader" OR "Flock Safety") W/25 (moratorium OR ban OR bans OR banned OR banning OR cancel! OR terminat! OR suspend! OR suspension OR "not renew" OR "did not renew" OR "declined to renew" OR "non-renewal" OR nonrenewal OR reject! OR "voted against" OR remov! OR "opt out" OR pause OR paused OR pausing) AND NOT (RCMP OR Ontario OR "prohibited driver")
```

*Step 4 — approvals, for the comparison group. Sample; do not exhaust:*
```
("license plate reader" OR ALPR OR "Flock Safety" OR "plate reader") W/25 (approv! OR authoriz! OR "voted to" OR "agreed to" OR renew! OR expand! OR install!) AND ("city council" OR "town council" OR "village board" OR "board of aldermen" OR alderman OR councilmember OR "council member")
```

**Exports currently on disk** (`external/source/nexis/`):

| file | documents |
|---|---|
| `q0_calibration_001-300.DOCX` | 300 |
| `q1_restrictive_2019-2021.DOCX` | 12 |
| `q1_restrictive_2022.DOCX` | 36 |
| `q1_restrictive_2023.DOCX` | 17 |
| `q1_restrictive_2024.DOCX` | 25 |
| `q1_restrictive_2025.DOCX` | 44 |
| `q1_restrictive_2026.DOCX` | 411 |
| `q2_ordinance_allv2.DOCX` | 62 |

Step 4 has **not** been run.

### 3b. DeFlock

The DeFlock activist project publishes a "wins" list from its CMS:

```
https://cms.deflock.me/items/flockWins?limit=-1
```

Public, no authentication, returns JSON. Snapshot saved at
`external/source/deflock/deflock_flockwins.json` (153 records). Re-fetch with
`curl` to refresh.

Its outcome vocabulary is coarser than ours — `Contract Canceled`,
`Cameras Deactivated`, `Contract Rejected`, `ALPRs Banned`,
`Contract Reinstated`. In particular **`Cameras Deactivated` does not
distinguish a pause from a permanent end**; it is mapped to `canceled` and
flagged, and that split must be made by reading the source.

**It is an advocacy project cataloguing victories.** That is a different
selection mechanism from press coverage, which is why combining the two works,
but it also means the register is not a neutral census. Both sources plausibly
under-record cities that quietly declined to renew without a public fight.

---

## 4. Pipeline

Three scripts, run in this order.

```bash
# 1. parse every Nexis export into candidate rows (staging, not the register)
.venv/bin/python external/parse_nexis.py external/source/nexis/*.DOCX

# 2. merge Nexis candidates with DeFlock into the register
.venv/bin/python external/merge_decision_sources.py

# 3. resolve the hand-maintained register to place GEOIDs
.venv/bin/python external/build_alpr_decisions.py
```

**`external/parse_nexis.py`** splits each `.docx` on Nexis's `End of Document`
separator, pulls the fixed header fields, and proposes a city, an action and a
reason. Writes `external/source/nexis/nexis_candidates.csv` (currently 907
rows). This is a **staging file**: the parser proposes, a human disposes.

**`external/merge_decision_sources.py`** unions Nexis and DeFlock on
`place_geoid`, records which sources support each row, and flags disagreement.
Writes `external/source/alpr_decisions_merged.csv` and
`external/source/alpr_decisions_counties.csv`.

**It is idempotent and protects human work.** Re-running preserves any row
marked `verified=TRUE` exactly as edited, refreshing only the provenance
fields. Delete the output file to rebuild from scratch.

**`external/build_alpr_decisions.py`** resolves city and state to a
7-character `place_geoid` against TIGER, validates the controlled vocabularies,
and refuses to guess: a name that repeats within a state is reported for manual
resolution rather than assigned to the first match.

**`external/table_decision_descriptives.R`** produces
`docs/table_decision_descriptives.tex`, summary statistics for the register
against the risk set.

---

## 5. Register schema

`external/source/alpr_decisions_merged.csv`, 20 columns.

| field | notes |
|---|---|
| `city`, `state`, `place_geoid` | `place_geoid` is **character, 7 chars**. Never read as numeric. |
| `action` | `ordinance_ban` · `canceled` · `suspended` · `not_renewed` · `declined_to_adopt` · `replaced_vendor` · `considered_no_action` · `adopted` |
| `decision_date` | when the body **voted**, `YYYY-MM[-DD]` |
| `action_date` | when it took **effect** — often months later |
| `adopted_date` | when the city first adopted, where known |
| `body` | `city_council` · `mayor` · `city_manager` · `police_chief` · `referendum` · `county_board` · `other` |
| `vote_for`, `vote_against` | council tallies |
| `reason` | `federal_immigration_access` · `privacy` · `unauthorized_access` · `cost` · `efficacy` · `other` |
| `reversed`, `reversal_date` | cities do reinstate |
| `source_type`, `source_url` | `ordinance` · `council_minutes` · `news` · `aggregator` |
| `verified` | **`TRUE` only after a human has read the source** |
| `sources`, `n_sources`, `source_conflict` | provenance |
| `notes` | free text |

Use `decision_date` for survival models; `action_date` lags it.

---

## 6. What has already been established

**The phenomenon is an 18-month event.** 89% of all coverage is dated 2025 or
2026. The 2019–2024 slices returned 90 documents between them and contained
essentially no municipal ALPR decisions. The risk period effectively starts in
2025, which is a finding, not a search failure.

**Neither source alone is adequate, and the gap is size-graded.**

| | n | median population |
|---|---|---|
| in both sources | 15 | 60,953 |
| Nexis only | 41 | 33,824 |
| DeFlock only | 95 | 17,600 |

Press coverage scales with city size; the activist tracker reaches further
down. This is the news-desert selection problem, measured rather than asserted,
and it is a methods-section paragraph.

**Codified bans are rare.** The ordinance query returned **one** clear case
(Columbia, MO, November 2024) out of 62 documents. Most cities suspend or
decline to renew rather than legislate. That is probably the real finding.

**Nexis yields roughly 32% duplicates and 16% irrelevant** even with grouping
on. The parser flags both rather than deleting them, so exclusions stay
auditable.

---

## 7. What remains

**a. Verification — the blocking task.** Nothing should be modelled until rows
are confirmed. Suggested order:

1. The **6 `source_conflict=TRUE` rows** first. These are where DeFlock and
   Nexis disagree on what happened, mostly `canceled` vs `suspended`, and they
   are where the coding judgment actually bites.
2. The **15 rows with `n_sources=2`**, corroborated by both.
3. The rest, sorted by `city_conf` in the staging file.

For each: read the source, set `verified=TRUE`, correct `action` and `state`,
and add `vote_for`/`vote_against` where the article reports a tally.

**b. Re-run the 2025 Nexis slice.** The export on disk used an earlier version
of the Step 3 query that included `AND ("city council" OR ...)`. That clause
over-restricted: 2025 returned 44 documents where the *narrower* calibration
query returned 46 for the same year. 2026, run with the corrected query,
returned 411. **2025 is the year the wave began and most of it has not been
retrieved.**

**c. Run Step 4** (approvals) to build the comparison group.

**d. Decide about counties.** 28 county-level decisions sit in
`alpr_decisions_counties.csv`. They are real decisions by a separate body — a
county board contracting for the sheriff — but have no `place_geoid` and cannot
join the place frame. Seven counties contain a municipality that also decided;
Dane County WI contains five. Those are separate votes, not duplicates.

**e. Sample-size reality.** With ~151 places and perhaps 40–48 surviving
verification at the Nexis end, the place-level ladder specification **cannot**
be run: that is 2–3 events per parameter against a conventional minimum of ten,
and county fixed effects are impossible. Plan for four or five covariates with
Firth penalised logistic regression, or a matched design pairing each decider
with adopting non-deciders on state, size and adoption timing.

---

## 8. Pitfalls

**City matching is a proposal, not a measurement.** Nexis has no municipality
field; the parser matches TIGER place names against the headline, then the lead
paragraph, preferring the state implied by the publication. `city_conf` is
`high` (headline match, state agrees), `medium` (headline, no state hint),
`low` (lead paragraph only). **Only high and medium are usable without
checking.**

**The `state` column is wrong more often than the city.** A wire service
dateline gives no state, so the parser falls back to population ranking. Two
confirmed examples: *Portsmouth* is **RI**, not VA; *Nashville* (Metro Council)
is **TN**, not NC. Both are real decisions with the wrong state attached.

**Place names that are ordinary words.** "Why, AZ", "Reader, WV",
"Council, ID", "Success, AR", "Texas City, TX" all matched prose. A stoplist in
`parse_nexis.py` suppresses the known offenders; expect new ones in new
batches.

**`PLACE_SUFFIX` from `place_police.py` must not be used here.** It strips the
bare word "city", turning *Iowa City* into *IOWA*, which then matches any
article mentioning the state. `parse_nexis.py` uses a narrower `GOV_SUFFIX`
that strips only parentheticals and consolidation phrases.

**Flock is headquartered in Atlanta**, so "Atlanta-based Flock Safety" appears
constantly and matched Atlanta on articles about other cities. Stripped before
matching.

**Nexis carries Canadian papers.** "Prohibited driver" is a Canadian traffic
offence; the term `prohibit!` pulled in 45 Canadian articles before it was
removed from the query and a filter added.

**Not every hit is a municipal decision.** State legislation, officer
misconduct, opinion letters, university police and Spanish/Portuguese wire
translations are each flagged with a `drop_reason` rather than deleted.

---

## 9. Files

```
external/source/
  alpr_decisions_merged.csv        the register -- 151 places, edit this one
  alpr_decisions_counties.csv      28 county decisions
  alpr_decisions.csv               early 13-row hand seed, superseded
  nexis/
    *.DOCX                         Nexis Uni exports
    nexis_candidates.csv           parser staging output, 907 rows
  deflock/
    deflock_flockwins.json         DeFlock CMS snapshot, 153 records
external/
  parse_nexis.py                   docx -> candidate rows
  merge_decision_sources.py        Nexis + DeFlock -> register
  build_alpr_decisions.py          city/state -> place_geoid
  table_decision_descriptives.R    summary statistics table
docs/
  table_decision_descriptives.tex
tests/
  test_alpr_decisions.py           6 tests, network-free
```

There is a stray byte-identical copy of `alpr_decisions_merged.csv` at the
repository root. It contains no edits and can be deleted.

## 10. Tests

```bash
.venv/bin/python -m pytest tests/test_alpr_decisions.py -q
```

Six tests, all network-free. They enforce the invariants that have already
broken once: that an empty `place_geoid` is never zero-padded into `"0000000"`
(this shipped, and silently resolved every row to a nonexistent place), that
ambiguous names are dropped rather than guessed, that a manual override keeps
its leading zero, and that the register retains approvals and not only refusals.
