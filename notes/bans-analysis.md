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

Stone's register (151 places + 28 counties, none verified) was re-read row by row against its
source by six parallel agents, and three more searched for decisions neither source had recorded
(DeFlock's CMS stopped updating in August 2026). Raw outputs, one CSV per batch, are in
`alpr_ban_dataset/verification/` with the coding instructions (`INSTRUCTIONS.md`).
`alpr_decisions_merged.csv` is untouched.

| | rows |
|---|---|
| Existing register: confirmed / not a decision / duplicate / unconfirmed | 158 / 14 / 3 / 4 |
| New from gap search (confirmed + unconfirmed) | 444 |
| Duplicate reports collapsed (same unit, same outcome, ≤45 days) | 136 |
| **In scope** (confirmed, restriction, resolved, ≤ cutoff) | **424** |

424 decisions = 272 by Census places (263 distinct), 41 by New England towns / townships
(county subdivisions, 36 distinct; outside the place universe, as the draft already says), 111 by
counties (104 distinct). 39 states. 66% dated Aug–Sep 2026.

What the verification found about the old register: the Nexis parser often took headline words as
cities ("Green, OH" = Ithaca NY, "Carrier, OK" = Harrisonburg VA, "Valley, AL" = Tempe AZ); 11
confirmed rows had the wrong jurisdiction and 57 had their action recoded, mostly DeFlock's
"Contract Canceled"/"Cameras Deactivated" hiding a pause or a non-renewal; many decisions were made
by a chief, sheriff or manager, not a vote.

**State-triggered decisions (41, flagged `state_triggered`):** Florida agencies acting on FDOT's
revocation of ALPR permits on state roads (Aug 31 2026; 33), Texas agencies acting on the
governor's grant-funding pause (6), Washington agencies complying with SB 6002 (2). Kept in the
counts and main models; column 5 of the model table drops them (Alex's call, 2026-10-26).

## Outcomes (the draft's three)

- `dv_pause` = suspended / paused pending review
- `dv_ban` = cancelled, not renewed, ordinance ban, or cancelled to switch vendor (the backlash is Flock-specific)
- `dv_any` = either, or rejected before adoption
- `dv_any_local` = `dv_any` excluding state-triggered decisions

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

## First results (Firth logit, 27,876 places, 260 acted; base rate 0.93%)

1-SD average marginal effects, percentage points (`output/tables/ban_model_ame.csv`):

| | any | ban | pause | any, local |
|---|---|---|---|---|
| Any camera (0→1) | +1.28 | +1.08 | +0.27 | +1.31 |
| Log population | +1.40 | +0.91 | +0.32 | +1.30 |
| County also restricted (0→1) | +1.21 | +0.97 | +0.36 | +1.06 |
| Incorporated (0→1) | +0.81 | +0.64 | +0.03 | +0.78 |
| Trump 2020 share | −0.47 | −0.34 | −0.11 | −0.47 |
| Share Black | −0.45 | −0.32 | −0.11 | −0.46 |
| Log median HH income | −0.41 | −0.28 | −0.14 | −0.39 |
| Log cameras (intensity) | −0.13 | −0.12 | +0.01 | −0.17 |

Reading: against a 0.93% base rate, a 1-SD more-Trump place is about half as likely to restrict;
restriction is a large-place, incorporated, already-adopted phenomenon that clusters within counties;
conditional on adopting, *more* cameras predicts *less* reversal. Robust to state FE (col. 4) and to
dropping state-triggered decisions (col. 5). Descriptive associations only.

## Caveats to carry into the text

- Coverage is a floor, not a census: two trackers claim 330+ cancellations; the gap search ran out of
  web-search budget, and MD, WV, DE, DC, MS, LA, NJ, VT, NH, NE, SD were thinly searched.
- 31 gap-search rows stayed `unconfirmed` (excluded). Some evidence quotes came through a page summariser —
  spot-check any quote before it goes in the paper.
- Several exact dates are inferred from "voted Tuesday" + article date (noted per row).
- Decisions after the cutoff (Tempe ordinance Oct 15, Richmond VA, Henrico, Fayetteville AR ban, Milwaukee
  County board, …) are listed in the agents' notes, not coded.
