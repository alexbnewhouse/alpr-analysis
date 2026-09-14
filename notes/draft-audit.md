# Draft audit — "What the Flock?"

*Read 2026-09-13. Source: `~/Dropbox/Apps/Overleaf/Memo: Flock Camera Adoption/main.tex` (993 lines, modified today) + `ref.bib` (11 entries). Read-only.*

**Coauthor:** Stone Neilon · **Venue:** APRL, **Fri Nov 6, 2026** · AI declaration footnote already in the title.

## The one-paragraph version

- Methods, data, and the two variable appendices are **done**.
- All six results tables **exist but are commented out** — both Results sections are empty.
- Theory section has real holes: Crime and Demographics are fragments; Governance says "TK THIS LIKELY DOESNT HAVE AN EFFECT?!"
- The "rejection" third of the title (bans/pauses) is **notes, not a section**.
- Your lane — crime, sheriff, police funding — is mostly **missing at the place level** and entirely missing at the tract level.

## Section by section

| § | Section | State | Missing |
|---|---|---|---|
| — | Abstract | 🟡 | Results sentence is "TK … TK … TK" |
| 1 | Intro | 🟡 | Results sentence TK |
| 2 | ALPR overview | 🟡 | Misuse examples ("officer TK … ex-girlfriend"; "HOA member in TK"); ICE paragraph is one sentence; Mourtgos & Adams result "a TK vehicle theft"; DHS 2025 report uncited |
| 3 | Different users | 🟡 | Public-sector paragraph is a list + a dangling sentence |
| 4 | Aggregate factors | 🔴 | **Crime** = 3 fragments ("CITE TK Unsure"); **Demographics** stops mid-sentence; **Governance** doubts itself; orphan sentences at lines 143–161 |
| 5 | Data | 🟢 | Says deflock.org; appendix says OSM/Overpass — reconcile. `tab:descriptives` referenced but **doesn't exist**. Street View check "planned" |
| 6 | Geographies | 🟡 | **Places subsection is empty.** Counties and Tracts written |
| 7 | Methods | 🟢 | Hurdle: logit + county FE for adoption; zero-truncated NB + Mundlak for intensity. Rationale given = "software limitations" |
| 8–9 | Adoption / Intensity Results | 🔴 | **Empty** |
| 10 | Banning | 🔴 | Two paragraphs + notes. LexisNexis + DeFlock "wins" plan; "Table TK", "September TK" cutoff |
| A | Appendix | 🟡 | Tract ✅ Place ✅ **County variable list missing.** "FE v. Mundlak comparison" is an empty heading |

## What's already in the models (from the commented tables)

- **County** (n = 2,562 / 1,880): demographics, scale, land use, **police spend per capita (CoG E62, FY2022, 26% imputed)**, county-govt share of police, unincorporated share, **violent + property crime rates** (source/year not stated), Trump 2020. State FE in the last column.
- **Place** (n = 23,855 / 7,033): same core + `incorporated`, `own_pd` (FBI CDE roster), precinct-apportioned Trump share. **Crime dropped** — only 11.9% of places have it.
- **Tract** (n = 82,728 / 38,412): demographics, scale, land use. **No crime, no police, no politics.**
- Excluded as collinear at county: # municipalities, # places with own PD, county ideology (`docs/vif_diagnostics.txt` → Stone has a repo).

## Headline patterns you should know cold

- **Scale wins everywhere.** Log population is the biggest coefficient at every level.
- **Retail/food job share and employment ratio are strongly positive at every level** — the parking-lot story has legs.
- **Race shares attenuate or flip once FE/Mundlak are in.** County share Black: 3.85 → −0.31 with state FE. Place share Black: 2.36 → 0.09 with county FE. **Tract share Black stays positive within county (0.495)** — the quotable finding, and the one people will ask about.
- **Trump share flips sign within county at the place level (−0.86).** Politics is a between-county story.
- Police spending: positive until state FE, then null. Property crime positive, violent crime null throughout.
- Own PD: small positive on adoption, null on intensity.

## Questions for Stone

1. Where's the repo (`docs/vif_diagnostics.txt`)? Can I get read access + the built panels so I add columns instead of rebuilding?
2. County crime source and year?
3. Is the "by margin" restructure (Adoption / Intensity) the plan, or are per-geography sections coming back?
4. Who owns the ban dataset? Coding sheet? Cutoff date?
5. Is the 1,000-camera Street View check happening? (Cheaper alternative: Flock transparency-portal counts.)
6. Tables or coefficient plots at APRL?
7. `\date{August 10, 2026}` and the "AES: 9-7-25" comment — placeholders?

## Small fixes for when the draft is unfrozen

- "aerial" → **areal** (×2) · "ALDR" → ALPR (×2) · "APLR" → ALPR
- "payed" → paid · "piece of mind" → peace · "roll of land use" → role · "feasable" · "interpretated" · "fined by Esri" → defined
- Duplicate `\usepackage{graphicx}`; `caption` loaded twice with different options
- One sentence in §5: "DeFlock is a front-end to OSM nodes tagged `surveillance:type=ALPR`; pulled via Overpass on <date>."
