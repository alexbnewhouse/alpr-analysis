# Methods: the ALPR pause/ban register and the place-level restriction models

*Written 2026-10-26 for the "Banning of Flock Cameras" section of "What the Flock?". Describes the
data in `register/alpr_decisions_verified.csv`, `../data/bans/`, and the outputs in
`../output/tables/tab_ban_*.tex` and `../output/figs/fig_ban_timeline.*`. Everything below can be
re-run from the repository (see §8). Citations marked **[cite]** still need a `.bib` entry.*

---

## 1. Unit of observation and scope

**Unit: the decision.** A decision is an act by a US local government — a council or commission
vote, a mayor's, manager's, police chief's, or sheriff's announcement, or a referendum — to
**pause, cancel, not renew, ban, or reject** automated license plate readers (ALPRs). One
jurisdiction can contribute several decisions (e.g. a pause followed weeks later by a cancellation).

**Jurisdictions covered.** Three kinds of general-purpose local government:

| type (`geo_type`) | what it is | identifier |
|---|---|---|
| `place` | an incorporated city, town, village or borough, or a Census-designated place (Census "place") | 7-character place GEOID |
| `cousub` | a New England town or a township government in MI, OH, NJ, PA, NY (Census county subdivision) | 10-character county-subdivision GEOID |
| `county` | a county or county-equivalent, including decisions by the county sheriff | 5-character county FIPS |

A decision by a city police department is attributed to its city; a decision by a sheriff is
attributed to the county. Consolidated city-counties (Jacksonville–Duval, Nashville–Davidson,
Indianapolis–Marion, Louisville–Jefferson, Athens–Clarke, Augusta–Richmond, Denver, San Francisco,
Kansas City–Wyandotte) are counted once, as the city. Universities, school districts, special
districts (e.g. a downtown development authority), state agencies, HOAs and businesses are coded
`level = other` and **excluded** from all tables and models (26 confirmed decisions).

**Time window.** Decisions dated **on or before 30 September 2026** are in scope. 79 confirmed
decisions dated 1–25 October 2026 are kept in `data/bans/bans_after_cutoff.csv` so the cutoff can be
moved without new collection; they are in no table or model. Seven in-scope decisions predate 2025.

**Vendor.** The register covers ALPR decisions regardless of vendor; 13 in-scope decisions concern
a vendor other than Flock Safety (flagged, and dropped in a robustness column). Cancelling Flock to
switch to another ALPR vendor is coded as a cancellation of Flock (`replaced_vendor`), because the
draft frames the backlash as Flock-specific.

---

## 2. Sources

Decisions were found through five kinds of source. Sources 1–2 seeded the register; 3–5 were
searched to find what 1–2 missed. Every decision that enters the analysis was then confirmed
against a **primary or local source** (§3) — the lists in 2–4 are treated as leads, never as evidence.

1. **Nexis Uni** (local news; Stone Neilon). Full-text news searches run before this pass. The
   exact query strings, settings and per-year export counts are in `HANDOFF_ban_dataset.md` §3a
   (calibration headline query; codified-ban query; main restrictive query run per year slice
   2019–2026; the approvals query was not run). A parser (`scripts/parse_nexis.py`) proposed a city,
   state and action for each article (907 candidate rows, `sources/nexis/nexis_candidates.csv`).
2. **DeFlock "wins" register.** `https://cms.deflock.me/items/flockWins?limit=-1` (153 records;
   re-fetched 2026-10-26 and unchanged — the feed stopped updating in August 2026).
   `scripts/merge_decision_sources.py` merged 1 and 2 into Stone's 151-place / 28-county register
   (`register/alpr_decisions_merged.csv`), of which **no row had been verified**.
3. **National activist trackers**, downloaded 2026-10-26 and parsed entry by entry
   (`verification/round2/tracker_entries.csv`): deflocktheusa.com/cancellations (341 entries) and
   whoapprovedthis.org/cancellations (332 entries). Each tracker entry links a per-jurisdiction page
   that usually names its source.
4. **An activist Google Sheet** of cancellations (461 rows, all states, with source URLs), exported as
   CSV on 2026-10-26 (`verification/round2/sheet_candidates.csv` holds the 64 rows not already in the
   register).
5. **Direct searches** of local news, local TV, state news services, government websites and
   council/board minutes (Legistar, CivicPlus, BoardDocs), state by state, plus per-state link lists
   at gettheflockoutofhere.com/database/<ST>/.

---

## 3. Collection and verification

### 3.1 Procedure

All verification and search was done on 2026-10-26 by parallel AI research agents (Claude, with web
search and page fetch), each working from the same written protocol
(`verification/INSTRUCTIONS.md`, and `verification/round2/ROUND2.md` / `RECONCILE.md` for later
rounds). **[AI-use statement: the draft's title footnote already declares Claude use; this pass
should be named there.]** Agents wrote one CSV row per lead; scripts, not agents, merged rows,
resolved identifiers, removed duplicates and applied the cutoff (§4).

| round | what was done | rows written | confirmed |
|---|---|---|---|
| 1a — verify | Each of Stone's 179 register rows (151 places + 28 counties) re-read against its source in 6 batches of ~30 | 179 | 159 |
| 1b — gap search | 3 regional agents (Midwest; South + Northeast; West + national lists) searched for decisions missing from Nexis and DeFlock | 444 | 439 |
| 2 — trackers, sweeps, re-checks | 104 tracker entries not in the register verified (2 agents); 35 rows still unconfirmed re-checked; side leads noted by earlier verifiers coded; 5 state-by-state sweeps (Mid-Atlantic + New England; South + Plains; Virginia + North Carolina; West + Mountain; a second pass on FL, TX, WI, MI, OH, MN, IN, MO including all 67 Florida counties) | 514 | 414 |
| 3 — sheet + reconciliation | 64 sheet rows not in the register verified; 121 field-level corrections to 93 existing rows (`verification/corrections_r3.csv`) | 64 | 5 |
| **total** | | **1,201** | **1,017** |

Row counts are after re-checks (a re-checked row keeps its original ID and its later reading
replaces the earlier one). Confirmed rows exceed in-scope decisions (660) because the build
then removes duplicates, `level = other` rows, non-restriction actions, and post-cutoff dates (§4).

The round-2 search was driven by evidence of under-coverage: round 1 exhausted the session's web
search allowance before several states were searched, and the trackers listed decisions the
register lacked. Saturation check: of the 461 sheet rows in round 3, 397 matched the register and
only 5 of the remaining 64 were new, confirmed decisions (55 were duplicates under another name).

### 3.2 Evidence standard

A row is `confirmed` only if the agent opened a source that states the action and its date — a
local news report, council or board minutes, an agenda item with its recorded outcome, or a
government release — and copied into the row:

- `evidence_url` — the page that settles it (often not the tracker's or register's link);
- `evidence_quote` — at most 25 words, verbatim, supporting the action and date.

In most round-2 and round-3 batches, a script checked that each quote appears verbatim on its page.
Some quotes were taken from a page-summary tool where sites blocked direct fetching; those rows are
noted, and any quote should be re-checked before it is reproduced in the paper.

Other statuses: `not_a_decision` (no local-government ALPR decision: state legislation, opinion,
misconduct coverage, a vendor's own pause, a different technology such as gunshot detection or
speed cameras, a vote that failed); `duplicate` (the same decision as another row — named in
`notes`); `unconfirmed` (no source settled it — usually blocked pages or headline-only evidence).
Only `confirmed` rows are analysed; 50 rows remain `unconfirmed`.

### 3.3 What verification changed

- **Jurisdiction errors.** The Nexis parser matched place names in headlines, so many rows named
  the wrong place (e.g. "Valley, AL" = Tempe, AZ; "Green, OH" = Ithaca, NY; "Carrier, OK" =
  Harrisonburg, VA). 11 confirmed rows from Stone's register had the wrong city or state.
- **Action errors.** 57 confirmed register rows were recoded, mostly where DeFlock's "Contract
  Canceled" or "Cameras Deactivated" was really a temporary pause or a non-renewal.
- **Tracker errors.** The trackers had the same problems (wrong states, e.g. "Custer County, SD" =
  Custer County, CO; "expirations" inferred from contract terms; approval dates in place of end
  dates; decisions about other technologies).
- **Reconciliation (round 3).** Conflicts between rounds were settled by re-reading sources:
  reversals were recorded (e.g. Cleveland's non-renewal reversed by a 9–6 extension on 2026-07-15),
  failed termination votes recoded as pauses (Lebanon, OH), and Florida rows coded consistently
  (§3.4).

### 3.4 Coding scheme

Controlled vocabularies (full list in `verification/INSTRUCTIONS.md`):

| field | values |
|---|---|
| `action` | `ordinance_ban` (codified prohibition) · `canceled` (contract terminated / cameras permanently removed) · `suspended` (paused, deactivated pending review) · `not_renewed` (contract allowed to lapse) · `declined_to_adopt` (proposal, pilot or grant voted down or withdrawn) · `replaced_vendor` · `considered_no_action` · `adopted` |
| `permanence` | `temporary` · `permanent` · `unclear` |
| `decision_date` | date the body decided or announced (`YYYY-MM-DD`, else `YYYY-MM`); `action_date` = date it took effect |
| `body` | `city_council` · `mayor` · `city_manager` · `police_chief` · `referendum` · `county_board` · `sheriff` · `other` |
| `vote_for`, `vote_against` | council tally where reported |
| `reason` | primary stated reason: `federal_immigration_access` · `privacy` (incl. general surveillance and data retention) · `unauthorized_access` (misuse, breaches, unapproved sharing, data resale) · `cost` · `efficacy` · `other`; `reason_secondary` likewise |
| `vendor` | `Flock` · `other:<name>` · `unknown` |
| `reversed`, `reversal_date` | the jurisdiction later reinstated ALPRs |
| `confidence` | `high` (primary or local source explicit on action and date) · `medium` · `low` |
| `state_trigger` | `yes` / `no` / `unclear` (§3.5) |
| `partial` | `yes` / `no` (§3.5) |

Dates are often inferred from relative wording ("voted Tuesday") plus the article's date; such rows
say so in `notes`. 502 of 660 in-scope decisions are dated to the day, 152 to the month, 6 not at all.

### 3.5 Flags

- **State-triggered** (`state_triggered = 1`; 102 in-scope decisions). The decision was made because
  of a state law, order or request rather than on local initiative: Florida agencies acting on the
  state Department of Transportation's revocation of ALPR permits on state roads (31 August 2026; 82),
  Washington agencies complying with SB 6002 (10), Texas agencies acting on the governor's pause of
  state grant funding (8), Vermont's ALPR statute (1), and the Connecticut governor's pause request
  (1). Round-2/3 agents coded this directly; for round-1 rows it was set from the verifier's notes
  and quote by state-specific keyword rules, with hand exceptions (see `STATE_TRIGGER` and
  `NOT_STATE_TRIGGERED` in `scripts/04_build_bans_register.py`). An agency that went beyond the
  state order (e.g. removing all cameras county-wide) is coded `no`. State-triggered decisions are
  **kept** in counts and main models and dropped in a robustness column (decision of 2026-10-26).
- **Partial** (`partial = 1`; 31). The decision covered only part of the jurisdiction's ALPR
  program: only cameras on state (or county) roads, only new installations or expansion, only some
  cameras, only private/HOA cameras. Removing a jurisdiction's only camera is not partial. Coded in
  round 3 for every row whose notes or quote suggested it (82 candidates found by keyword); five
  Florida rows and one Massachusetts row could not be settled and are coded not partial. Kept in the
  main models; dropped in a robustness column. Florida agencies that removed only state-road cameras
  to comply with the DOT order are therefore `confirmed`, `suspended`, `state_trigger = yes`, `partial = yes`.
- **Reversed** (15 in-scope decisions). Kept: the decision happened.

---

## 4. From verified rows to the analysis files

`scripts/04_build_bans_register.py` (Python; geopandas) does the following, in order.

1. **Stack and validate.** Reads every batch CSV in `verification/` (`out_*`, `gap_*`), applies
   re-checks (`recheck_*`: a later reading replaces the earlier row with the same ID) and field-level
   corrections (`corrections_*`, applied in file order), and blanks any value outside the controlled
   vocabularies (none were found in the final build).
2. **Resolve identifiers.** Each jurisdiction is matched by state and normalised name against the
   Census 2023 cartographic boundary files: places (`cb_2023_us_place_500k`), county subdivisions
   (`cb_2023_us_cousub_500k`, excluding CCDs, census subareas and unorganised territory), and
   counties (`cb_2023_us_county_500k`). Normalisation lower-cases, expands "St." to "Saint", and
   strips legal descriptors ("city", "town", "village", "borough", "township", "charter",
   "consolidated/metropolitan government", "(balance)"). Ties are broken toward incorporated places
   (e.g. El Cerrito city over El Cerrito CDP), then toward cities (Waukesha city over village); a name
   that matches no place falls back to county subdivisions. The script never guesses: an unresolved
   or still-ambiguous name is reported and excluded (none in the final build). Hand mappings exist
   for consolidated governments and one spelling (North Attleboro → North Attleborough).
3. **Scope.** `in_scope` = confirmed, `action` ∈ {ordinance_ban, canceled, not_renewed,
   replaced_vendor, suspended, declined_to_adopt}, `level` ∈ {place, county}, a resolved identifier,
   and `decision_date` ≤ 2026-09-30 (undated rows kept).
4. **De-duplicate.** The same decision was often reported by several sources or agents. Within a
   jurisdiction and outcome category (pause / ban / rejected), reports dated within **45 days** of each
   other (or one undated) are one decision; the best-evidenced report is kept (confidence high >
   medium > low; ties to the original register row). Reports on either side of the cutoff are
   de-duplicated separately. A pause followed by a cancellation remains two decisions. 216 reports
   were collapsed this way, in addition to the 85 rows agents themselves coded `duplicate`.
5. **Outcomes and outputs** (§5.1): the full audit trail
   (`register/alpr_decisions_verified.csv`, 1,201 rows with status, evidence, flags, `dup_of`),
   in-scope decisions (`data/bans/bans_quick.csv`, 660), one row per jurisdiction with outcome
   indicators (`place_decisions.csv`, 398; `cousub_decisions.csv`, 41; `county_decisions.csv`, 159),
   post-cutoff decisions, and `build_report.md`. Invariants are asserted (identifier widths; no
   post-cutoff or unconfirmed rows in scope).

**Result.** 660 decisions by 598 jurisdictions in 46 states: 440 by Census places (398 distinct), 46 by
towns/townships (41), 174 by counties (159). 68% are dated August–September 2026.

---

## 5. Variables

### 5.1 Dependent variables (place level)

A place is coded 1 if it has at least one in-scope decision of the given kind; otherwise 0.

| variable | definition | places = 1 in model sample |
|---|---|---|
| `dv_any` — **any restriction** | any pause, ban (below) or rejection before adoption | 394 |
| `dv_ban` — **ban** | `canceled`, `not_renewed`, `ordinance_ban`, or `replaced_vendor` | 251 |
| `dv_pause` — **pause** | `suspended` | 128 |
| `dv_any_local` | `dv_any`, excluding state-triggered decisions | 341 |
| `dv_any_whole` | `dv_any`, excluding partial actions | 383 |
| `dv_any_highconf` | `dv_any`, high-confidence evidence only | 243 |
| `dv_any_flock` | `dv_any`, excluding decisions about another vendor | 385 |

These follow the draft's plan of separate pause and ban variables plus an "any restriction"
indicator; rejection before adoption counts toward "any" only.

### 5.2 Place universe

Stone's place analysis frame (`alpr_handoff/external/data/model_frame_place.parquet`, 32,041 places),
restricted to places with **positive population and observed median household income**: **28,298
places**. This reproduces every place-column entry of the draft's descriptive table
(`tab:descriptives`) to three decimals. Four restricting places fall outside it and are dropped. Towns
and townships are not Census places and are outside this universe (as the draft already states);
their decisions are counted in Table `tab:ban-counts` only.

**Model sample:** the universe less places without 2020 vote data (Alaska, Hawaii, and places with
no reallocated returns): **27,876 places**, 394 with any restriction (base rate 1.41%).

### 5.3 Independent variables

All are on the scale used in the draft's place models unless noted.

| variable | construction | source |
|---|---|---|
| **Any camera** (adoption) | 1 if ≥ 1 mapped ALPR in the place | handoff frame (`has_camera`): OpenStreetMap ALPR nodes harvested through DeFlock/Overpass (124,416 cameras), point-in-polygon to places |
| **Log cameras** (intensity) | log(1 + number of mapped ALPRs) | handoff frame (`n_cameras`) |
| **Log population** | log(population) | ACS 2019–2023 5-year (handoff frame) |
| **Log median HH income** | log(median household income) | ACS 2019–2023 (handoff frame) |
| **Poverty rate** | share below the poverty line (proportion) | ACS 2019–2023 |
| **Share Black**, **Share Hispanic** | proportions; White non-Hispanic is the omitted reference | ACS 2019–2023 |
| **Trump 2020 vote share** | Trump votes / all presidential votes, 2020 | VEST 2020 precinct returns reallocated to 2020 block groups ("RLCR", main method, contiguous US) **[cite]**; block-group votes summed over block groups whose interior point lies in the place; a place containing no block-group interior point takes the share of the block group containing the place's interior point (`scripts/03_place_politics_governance.py`) |
| **Incorporated** | 1 unless the place is a Census-designated place (LSAD 57) | Census 2023 cartographic place file |
| **Own police department** | 1 if the place's government reports current police operations spending (item E62 > 0) | 2022 Census of Governments, Finance individual-unit file (`scripts/01_cog2022_police.R`) |
| **County also restricted** | 1 if the place's county has any in-scope county-level decision (any category, including state-triggered) | this register |

Validation of the constructed measures against the draft's descriptive table: Trump 2020 mean 0.611
(N = 27,876) vs the draft's 0.595 (N = 25,295), correlation 0.986 with the American Ideology Project's
place-level 1 − Democratic share on 6,201 cities **[cite]**; incorporated 0.666 vs 0.665; log own police
spending per capita 2.424 vs 2.416. **Own police department differs: 0.480 here vs 0.367 in the draft**,
which uses an FBI-roster flag; the draft's column should replace this one when available.

Descriptive-table-only variables (Table `tab:ban-descriptives`) follow the draft's definitions: share
Asian, share renter-occupied, median age, log land area, log arterial road km (log of km, 0 where the
place has no arterial road) and an arterial-road indicator, employment ratio, retail/food job share, log
own police spending per capita (log(1 + $ per capita), 0 without own police), and AIP MRP ideology
(2017–2021 survey period; cities above roughly 20,000 residents) **[cite]**.

Kept deliberately small: with 394 events and 11 slopes there are ~36 events per parameter; the pause
outcome (128 events) is near the conventional floor. Excluded as collinear with income or as
consequences of urban form, following the handoff's adoption models: per-capita income, home value,
rent, education, and commuting variables.

---

## 6. Models

### 6.1 Main specification (Table `tab:ban-models`)

For place *i* and outcome *y* ∈ {any, ban, pause}:

  logit Pr(y_i = 1) = α + β₁·AnyCamera_i + β₂·log(1 + Cameras_i) + **x**_i′**γ**

where **x** holds log population, log median household income, poverty rate, share Black, share
Hispanic, Trump 2020 share, incorporated, own police department, and county also restricted.

Camera exposure enters as both margins of the draft's hurdle — whether the place has any mapped
camera, and how many — as the draft's notes ask ("include controls for the adoption and intensity of
cameras"). Places without cameras stay in the sample: they can still reject a proposal, and some
cancelling places have no mapped camera because mapping is incomplete.

- **Columns 1–3: Firth penalised-likelihood logit** (`logistf::logistf`, `plconf = NULL`), chosen
  because restriction is rare (0.5–1.4%). Standard errors are the square roots of the penalised
  covariance diagonal; *p*-values (and stars) come from the penalised likelihood-ratio test, so a star
  can differ from what coefficient/SE alone would suggest.
- **Column 4: ordinary logit with state fixed effects** (`fixest::feglm`, binomial), standard errors
  clustered by state. States with no restricting place drop out (42 states retained; 25,964 places).

### 6.2 Robustness (Table `tab:ban-models-robust`)

The column-1 model (any restriction, Firth) re-estimated with the outcome redefined: (1) local
initiative only (`dv_any_local`); (2) whole-program decisions only (`dv_any_whole`); (3) high-confidence
evidence only (`dv_any_highconf`); (4) Flock only (`dv_any_flock`); and (5) the sample restricted to
places with at least one mapped camera — the risk set for reversal (8,032 places; the adoption dummy
drops out).

### 6.3 Marginal effects

Average marginal effects are reported in the text (`output/tables/ban_model_ame.csv`) using the
observed-value approach of Hanmer and Kalkan (2013), as the draft does for adoption: each place's
probability is predicted at its observed covariates, recomputed after raising one covariate by one
standard deviation of the model sample (binary covariates: set 0, then 1), and the differences are
averaged. Predictions use Firth's slopes with the intercept re-estimated (FLIC; `logistf::flic`),
because the Firth intercept inflates predicted probabilities for rare outcomes.

### 6.4 Interpretation

Associations, not effects. In particular: a place's camera count measures volunteer mapping as well as
deployment (handoff §2); restriction is recorded only where it was publicised; and covariates are
measured before 2026 while decisions cluster in August–September 2026.

---

## 7. Tables and figure

| output | content |
|---|---|
| `tab_ban_counts.tex` (`tab:ban-counts`) | in-scope decisions by action, by outcome category (plus how many followed a state action), by primary stated reason, and by period; columns places / towns / counties / total / %; states with ≥ 8 decisions in the notes |
| `tab_ban_descriptives.tex` (`tab:ban-descriptives`) | mean and SD of model variables for places that restricted (394), places with ≥ 1 camera that did not (7,702), and all places (28,298) |
| `tab_ban_models.tex` (`tab:ban-models`) | §6.1 |
| `tab_ban_models_robust.tex` (`tab:ban-models-robust`) | §6.2 |
| `fig_ban_timeline.pdf` (`fig:ban-timeline`) | decisions per month, January 2025–September 2026, stacked by ban / pause / rejection, with decisions that followed a state action shown separately in grey (7 pre-2025 and 6 undated decisions not shown) |

Tables are written by `scripts/05_bans_analysis.R` in the draft's style (booktabs, threeparttable,
coefficient with SE in one cell, notes below) and compiled in the draft's table preamble with no errors
or overfull boxes (`output/compile_check.tex`). They reference the draft's `tab:descriptives` label.

---

## 8. Reproducing

From the repository root:

```bash
# place covariates (needs data/raw/tiger/cb_2020_us_bg_500k.zip and the alpr_pipeline cache)
~/flock_research/.venv/bin/python scripts/03_place_politics_governance.py
# register: stack verification batches -> resolve -> de-duplicate -> outcomes
~/flock_research/.venv/bin/python scripts/04_build_bans_register.py
# tables, figure, marginal effects
Rscript scripts/05_bans_analysis.R
# compile check
cd output && pdflatex compile_check.tex
```

Software: Python with geopandas 1.1.4, pandas 3.0.5, shapely 2.1.2; R 4.6.1 with logistf 1.26.1,
fixest 0.14.2, arrow 26.0.0, dplyr 1.2.1, ggplot2 4.0.3. Census boundary files are downloaded from
`www2.census.gov/geo/tiger/GENZ2020|GENZ2023/shp/`. The verification step itself (agents reading web
sources) is not mechanically reproducible; its full output — every row with its URL, quote, status and
notes — is committed in `verification/` and is the record to audit.

---

## 9. Known limitations

- **Coverage is a floor.** Near-saturated against public lists, but decisions no one publicised are
  missing; small places are likelier to be missed, and Nexis coverage is size-graded (handoff §6).
- **50 rows remain unconfirmed** and are excluded.
- **Some quotes** were taken through a page summariser; re-check before quoting.
- **Inferred dates** (relative weekday wording) and **unsettled rows**: Waupaca, WI (undated memo);
  Winter Springs, FL (vendor unconfirmed); Neptune Beach, FL (date and scope); partial status of City of
  Alachua, Edgewater, Leesburg and Neptune Beach (FL) and Easthampton (MA).
- **Coding judgments** with defensible alternatives are noted per row (e.g. a council resolution or
  executive order coded `ordinance_ban`; "tabled" coded `declined_to_adopt` vs `considered_no_action`).
- **The camera intensity coefficient is fragile**: negative and significant for any restriction, but not
  for bans alone, with state fixed effects, with high-confidence evidence only, or among adopters only.
