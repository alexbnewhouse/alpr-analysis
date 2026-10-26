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

## Results (Firth logit, 27,876 places, 394 acted; base rate 1.41%)

1-SD average marginal effects, percentage points (`output/tables/ban_model_ame.csv`):

| | any | ban | pause | any, local |
|---|---|---|---|---|
| Any camera (0→1) | +1.94 | +1.44 | +0.61 | +1.84 |
| County also restricted (0→1) | +2.20 | +1.25 | +1.12 | +0.97 |
| Log population | +1.99 | +1.01 | +0.71 | +1.75 |
| Incorporated (0→1) | +1.34 | +0.90 | +0.37 | +1.10 |
| Share Black | −0.72 | −0.46 | −0.24 | −0.69 |
| Trump 2020 share | −0.62 | −0.44 | −0.16 | −0.62 |
| Log median HH income | −0.55 | −0.35 | −0.26 | −0.49 |
| Log cameras (intensity) | −0.20 | −0.10 | +0.01 | −0.24 |

Reading: against a 1.41% base rate, a 1-SD more-Trump place is ~45% less likely to restrict; restriction
is a large-place, incorporated, already-adopted phenomenon that clusters within counties (the county
coefficient halves without state-triggered decisions — the Florida wave was county-wide); conditional on
adopting, *more* cameras predicts *less* restriction — but that intensity term is the fragile one: significant
for any restriction and the local / whole-program / Flock-only variants, not for bans alone, with state FE,
high-confidence evidence only, or adopters only. Everything else (adoption, size, incorporation, county
clustering, Trump share, share Black, income) holds with state FE (`tab:ban-models` col. 4) and in all five
robustness columns.
Descriptive associations only. (The round-1 version, 260 events, had the same signs and significance.)

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
