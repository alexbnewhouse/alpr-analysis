# Bans / pauses — data and first analysis (2026-10-26)

For the draft's "Banning of Flock Cameras" section (the "ALEX INCLUDE CONTROLS FOR THE
ADOPTION AND INTENSITY OF CAMERAS" note and "Table TK"). Cutoff **2026-09-30**.

## Pipeline

```
scripts/03_place_politics_governance.py   place Trump 2020, incorporated, own PD, own police $ p.c.  -> data/out/place_politics_governance.csv
scripts/04_build_bans_register.py         verification pass -> verified register + per-unit outcomes   -> data/bans/*, alpr_ban_dataset/register/alpr_decisions_verified.csv
scripts/05_bans_analysis.R                tables + figure                                             -> output/tables/*, output/figs/*
output/compile_check.tex                  compiles the outputs in the draft's table preamble (0 overfull boxes)
```

Python scripts run with `~/flock_research/.venv/bin/python` (geopandas). Raw inputs:
`data/raw/tiger/cb_2020_us_bg_500k.zip`, `cb_2023_us_cousub_500k.zip` (Census GENZ), plus the
alpr_pipeline cache (VEST block-group returns, 2023 place/county boundaries, AIP).

## The register

Built in three passes on 2026-10-26, all raw outputs in `alpr_ban_dataset/verification/` (one CSV per
batch, with the coding instructions `INSTRUCTIONS.md`; round-2/3 briefs and inputs in `round2/`).
`alpr_decisions_merged.csv` (Stone's) is untouched.

1. **Verification + first gap search.** Stone's register (151 places + 28 counties, none verified) re-read
   row by row against its source (6 agents); 3 more searched for decisions neither source had recorded
   (DeFlock's CMS stopped updating in August 2026). Web-search budget ran out partway.
2. **Round 2** (search cap raised): every entry of two national trackers (deflocktheusa.com 341,
   whoapprovedthis.org 332) matched to the register and the 104 unmatched verified; the 35 unconfirmed rows
   re-checked; verifiers' side leads coded; five state-by-state sweeps (Mid-Atlantic/New England, South/Plains,
   VA/NC, West, and a second pass on FL/TX/WI/MI/OH/MN/IN/MO incl. all 67 Florida counties).
3. **Round 3**: an activist Google Sheet (461 rows, all states) matched — 397 already present, the 64 others
   verified (5 new); a reconciliation pass applied 121 field-level corrections (`corrections_r3.csv`):
   reversals, recodes, Florida compliance-only rows, and the `partial` flag.

| | rows |
|---|---|
| Rows reviewed in total | 1,201 |
| Existing register: confirmed / not a decision / duplicate / unconfirmed (after re-check) | 159 / 15 / 4 / 1 |
| Rounds 2–3: confirmed / duplicate / not a decision / unconfirmed | 419 / 76 / 34 / 49 |
| Duplicate reports collapsed (same unit, same outcome category, ≤45 days) | 216 |
| **In scope** (confirmed, restriction, resolved, ≤ cutoff) | **660** |
| Confirmed, after the cutoff (`data/bans/bans_after_cutoff.csv`) | 79 |

660 decisions = 440 by Census places (398 distinct), 46 by New England towns / townships (county
subdivisions, 41 distinct; outside the place universe, as the draft already says), 174 by counties
(159 distinct). 46 states. 68% dated Aug–Sep 2026. Saturation check: the round-3 sheet added only 5.

What the verification found about the old register: the Nexis parser often took headline words as
cities ("Green, OH" = Ithaca NY, "Carrier, OK" = Harrisonburg VA, "Valley, AL" = Tempe AZ); 11
confirmed rows had the wrong jurisdiction and 57 had their action recoded, mostly DeFlock's
"Contract Canceled"/"Cameras Deactivated" hiding a pause or a non-renewal; many decisions were made
by a chief, sheriff or manager, not a vote. The trackers have the same problems (wrong states,
inferred "expirations", approval dates instead of end dates).

**Flags** (kept in counts and main models; robustness table drops each in turn):
- `state_triggered` (102): decisions made because of a state law, order or request — Florida agencies on
  FDOT's Aug 31 2026 revocation of ALPR permits on state roads (82), Washington SB 6002 (10), the Texas
  governor's grant-funding pause (8), Vermont's ALPR statute, the Connecticut governor's pause request.
  Alex's call (2026-10-26): keep, flag, robustness.
- `partial` (31): covers only part of a program — state-road cameras only, new installs only, some cameras,
  county roads only. Removing a jurisdiction's only camera is not partial.
- `vendor` (13 non-Flock), `confidence` (391 high), `reversed` (later reinstated; still counted — the decision happened).

## Outcomes (the draft's three)

- `dv_pause` = suspended / paused pending review
- `dv_ban` = cancelled, not renewed, ordinance ban, or cancelled to switch vendor (the backlash is Flock-specific)
- `dv_any` = either, or rejected before adoption
- `dv_any_local` = `dv_any` excluding state-triggered decisions
- `dv_any_whole`, `dv_any_highconf`, `dv_any_flock` = `dv_any` excluding partial actions / keeping high-confidence
  evidence only / Flock contracts only (robustness table, `tab:ban-models-robust`)

## Reproducing the draft (handoff frames)

- Place universe: `model_frame_place` with population > 0 and observed median income gives **N = 28,298**
  and reproduces every place-column entry of `tab:descriptives` to three decimals (log arterial road km = log(km),
  0 where no arterial road).
- Built here because the handoff frame lacks them:
  - Trump 2020: block-group VEST returns summed within places (interior points), else the containing block group.
    Mean 0.611 (N 27,876) vs the draft's 0.595 (N 25,295); r = 0.986 with AIP 1 − demshare on 6,201 cities.
  - Incorporated (LSAD ≠ 57): 0.666 vs draft 0.665.
  - Log own police spending p.c. (CoG 2022 E62): 2.424 vs draft 2.416.
  - **Own police department differs:** 0.480 (CoG E62 > 0) vs the draft's 0.367 (Stone's FBI-roster flag). If Stone's
    column is available it should replace this one.
- Adoption/intensity tables (county 2,468 / place 17,323 / tract 69,771) were **not** re-run here; Stone's current
  model code is not in the handoff.

## Results (Firth logit, full place specification, 26,926 places, 394 acted; base rate 1.46%) — re-estimated 2026-10-29

**Specification.** The first version used an 11-covariate short set (any camera, log cameras, log pop, log income,
poverty, share Black, share Hispanic, Trump 2020, incorporated, own PD, county also restricted). That was sized for
the ~45 events Stone's handoff expected. With 394 / 251 / 128 events the models now carry the draft's full place
adoption specification (`tab:crosslevel-adoption`, place column) plus camera exposure and county also restricted:
21 slopes, about 19 events per parameter for any restriction and 12 for bans. **Pause** (128 events) keeps the short
set plus share Asian (12 slopes, ~10.7 per parameter). **Change in white share is omitted**: it is not in the handoff
frame and needs ACS B02001 for 2015 and 2020 (no Census API key here). Listwise N falls from 27,876 to 26,926 (LEHD
job variables); no restricting place is lost. Race reference category: everyone not counted as Black alone, Asian
alone, or Hispanic (the old note's "white non-Hispanic" was wrong).

1-SD average marginal effects, percentage points (`output/tables/ban_model_ame.csv`; pause uses its own 12-covariate model):

| | any | ban | pause | any, local |
|---|---|---|---|---|
| Any camera (0→1) | +1.89 | +1.45 | +0.62 | +1.80 |
| County also restricted (0→1) | +2.19 | +1.27 | +1.14 | +0.99 |
| Log population | +1.44 | +0.55 | +0.71 | +0.99 |
| Incorporated (0→1) | +1.40 | +0.95 | +0.37 | +1.14 |
| Share Black | −0.76 | −0.49 | −0.25 | −0.73 |
| Trump 2020 share | −0.72 | −0.51 | −0.19 | −0.70 |
| Share Hispanic | −0.35 | −0.25 | −0.10 | −0.36 |
| Log density squared | −0.33 | −0.21 | | −0.24 |
| Log median HH income | −0.32 | −0.26 | −0.23 | −0.32 |
| Poverty rate | −0.32 | −0.23 | −0.18 | −0.30 |
| Share renter-occupied | +0.31 | +0.19 | | +0.30 |
| Share Asian | −0.19 | −0.09 | −0.08 | −0.15 |
| Log cameras (intensity) | −0.21 | −0.11 | +0.02 | −0.24 |

Reading: against a 1.46% base rate, a 1-SD more-Trump place is about half (49%) as likely to restrict. Restriction
is a large-place, incorporated, already-adopted phenomenon that clusters within counties (county coefficient 1.19 →
0.70 without state-triggered decisions). Same as before: Trump, share Black, share Hispanic, income, size,
adoption and county clustering are significant in every column of both tables, state FE included; incorporation is
significant everywhere except the pause column; own PD and own police spending are never significant; poverty drops out under state FE
(and is only p < .1 for bans, Flock-only and adopters-only). The intensity term is still fragile: significant for
any, local, whole-program, Flock-only; not for ban, pause, state FE, high-confidence, or adopters.

New in the full spec: share Asian is negative (significant in every column; p < .1 for bans and high-confidence);
renter share is positive for any restriction (p < .05) and in four of five robustness columns, but not for bans,
under state FE, or with high-confidence evidence; log density squared is negative throughout (restriction is least
likely at the density extremes). Log land area is positive for bans (p < .05) and in four robustness columns but not
for any restriction or under state FE. Roads and employment ratio are null; median age is significant only under
state FE and (p < .1) local initiative; retail/food share is p < .1 in four columns. Adding these covariates shrinks log population (0.59 → 0.47) and log income (−1.22 →
−0.63) and makes Trump larger (−3.34 → −4.01).
Descriptive associations only.

## Caveats to carry into the text

- Coverage is near-saturated against public lists (the last 461-row list added 5), but it is still a floor:
  decisions nobody publicized are missing, and MS, LA, ND, KS, DE, DC and NH have few for real reasons (NH's
  2016 ALPR law; little Flock).
- 50 rows remain `unconfirmed` (excluded) — mostly blocked sources or headline-only evidence.
- Evidence quotes were script-checked against page text in most batches, but some came through a page
  summariser — spot-check any quote before it goes in the paper.
- Several exact dates are inferred from "voted Tuesday" + article date (noted per row). Unsettled: Waupaca WI
  (undated memo), Winter Springs FL (vendor unconfirmed), Neptune Beach FL (date/scope), and the partial status
  of City of Alachua, Edgewater, Leesburg, Neptune Beach, Easthampton.
- October is busy (Tempe ordinance, Richmond VA, Henrico, Fayetteville AR, Milwaukee County, New Bedford, …);
  79 confirmed October decisions are in `bans_after_cutoff.csv` if the cutoff moves.
