# Data sourcing guide — crime, police & sheriff funding, and friends

*Written 2026-09-13. Organised by decisional unit: counties = sheriff's unit, places = police department's unit, tracts = nobody's unit. **[verified]** = checked against the source this session. **[verify]** = from memory; confirm before relying on it.*

## TL;DR

- **Biggest cheap win:** the 2022 Census of Governments has police spending for **every municipality**, not just counties. Nobody has pulled it. One download.
- **The 11.9% place-crime coverage is structural**, not a data failure: ~12,500 of ~31,000 places are CDPs with no government, and most small towns contract with the sheriff. Fix = (a) push coverage to its ceiling for places with a PD, (b) give everyone else the **county** crime rate as a cross-level covariate.
- **Motor vehicle theft** is the crime ALPRs are sold on. It's in every source below. Add it.
- **Flock's own transparency portals** (1,500+ agencies) expose per-agency camera counts. That's your validation set *and* a public/private split.
- Governance typology and HOAs: no good national data. Say so and move on.

## 0. Already in the models

- **County:** log police spend per capita (CoG **E62**, FY2022; 26% imputed), county-govt share of police, unincorporated share, violent + property crime rates (source/year unstated), Trump 2020.
- **Place:** `own_pd` (FBI CDE roster, spatial join), `incorporated`, precinct Trump share. Crime dropped.
- **Tract:** nothing on crime, police, or politics.

## 1. Crime

### County

- **Kaplan, Offenses Known & Clearances by Arrest (Return A), openICPSR 100707** [verified: 1960–2024]
  - Agency-year counts: murder, rape, robbery, agg. assault, burglary, larceny, **MVT**, arson. FIPS codes attached via LEAIC.
  - Caveat: FBI retired the summary system after 2020; **2021 is a hole** (big agencies missing). Use a **2017–19 mean** or **2022–23**.
  - Do: aggregate ORI → county; compute `coverage = pop of reporting agencies / county pop`; flag < 80%.
- **FBI Crime Data Explorer API** [verified site; endpoint from memory]
  - 2024: 16,000+ agencies, **95.6% of population** [verified]. Needs an api.data.gov key.
  - Agency roster has ORI, type, county, lat/lon — what Stone used for `own_pd`.
- **CDC WONDER homicide** (ICD-10 X85–Y09) [verify codes]
  - Vital statistics → **complete coverage, no reporting-agency problem**.
  - Suppressed under 10 → pool 2018–22, rate per 100k. Best robustness column for "violent crime".
- **ICPSR county-level UCR files** — **avoid.** Imputation is known-bad (Maltz & Targonski 2002); series ends 2016. Cite them if a reviewer asks why.

### Place

- **Kaplan + LEAIC** (ICPSR 35158, 2012 vintage) [verified series]
  - ORI → FIPS place directly. LEAIC is stale but ORIs rarely change; patch new agencies with the CDE roster.
  - Expect **~35–40% of places, 80–90% of population**, near-complete above 10k. Beat 11.9%.
  - Keep agencies with 12 months reported (field is in Kaplan's file).
- **Places without a PD:** use the sheriff's ORI rate or the county total. This is a **county-level covariate for a place-level outcome** — the multilevel move.
  - Consider `own_pd × crime`: crime should matter where there's a PD to buy cameras.

### Tract

- No official series. In order of usefulness:
  - **Gun Violence Archive** — every shooting since 2014, geocoded, national. Aggregate 2019–23 → `shootings_per_1k`. [verify bulk export]
  - **City open-data portals** (~100 big cities; PDAP indexes them) → big-city tract subsample only.
  - Commercial (AGS CrimeRisk, CoreLogic) — paywalled. Skip.
- Use GVA as one robustness column. Keep the paper's honest sentence that tract crime "does not exist."

## 2. Police & sheriff funding and capacity

- **2022 Census of Governments, Finance — Individual Unit File** [verified: released Oct 31, 2024]
  - Every government's finances by item code. Police: **E62** current ops, **F62** capital outlay [verify letters against the classification manual].
  - 2022 is a *census* year → all ~90,000 governments, no sampling.
  - **This is the missing place-level police budget.** Crosswalk: 14-char GOVS ID → FIPS via the GID file in the release. Keep the imputation flag.
- **2022 CoG Employment (ASPEP)** [verify file]
  - FTE + payroll by function; police function 62 splits sworn vs civilian. → officers per 1,000.
- **CSLLEA 2018** (ICPSR 38771) [verified]
  - All 17,541 agencies: sworn/civilian, **functions** (does the sheriff patrol, or only run the jail?).
- **LEMAS 2020** (ICPSR 38651) [verified]
  - ~3,500-agency sample; **asks whether the agency uses ALPRs** (also 2007/12/16) [verified].
  - Use: among "yes" agencies, what share show ≥1 OSM camera? Also gives you the BJS headline (~90% of sheriffs with 500+ deputies).
- **Flock transparency portals** (transparency.flocksafety.com/<agency>) [verified: 1,500+ agencies]
  - Per agency: **number of cameras**, searches/30 days, hotlist hits, retention days, sharing partners.
  - Scrapers: `mcclatchy-southeast/private_eyes` (MIT; NC + ~360 national portals, Jul 2023–Apr 2024) · `pmocek/scrape-flock-safety-subscriber-portals` (git-scraper, WA-focused).
  - Use: validate OSM counts agency-by-agency; split public vs private cameras; the sharing network is a second paper.
- **EFF Atlas of Surveillance** (CSV download) [verified: ~5,500 agencies]
  - Agency × technology with vendor and source. A "known ALPR user" flag from public records.

**Deliverables (one CSV each, GEOID-keyed):**
- `place_police.csv` — `GEOID, govs_id, police_current_E62, police_capital_F62, police_fte, sworn_2018, imputed_flag`
- `county_sheriff.csv` — `GEOID, sheriff_current_E62, sheriff_sworn_2018, sheriff_does_patrol, sheriff_elected, sheriff_287g, lemas_alpr_2020`
- `place_crime.csv` — `GEOID, ORI, months, violent_rate, property_rate, mvt_rate, covered_pop_share`
- `county_crime.csv` — same + `coverage_share, homicide_rate_cdc`
- `agency_flock.csv` — `agency, n_cameras_portal, searches_30d, n_sharing_partners, portal_date`

## 3. Sheriff institutions (county)

- **Elected vs appointed** — cheap dummy. Exceptions [verify each]: CT (no county sheriffs), RI (appointed), HI (state sheriff), AK (no counties), Denver/Broomfield, NYC, some consolidated city-counties.
- **Farris & Holman, *The Power of the Badge*** [verified: PSQ review 2026] + Farris's 5,500-election dataset [verified] — party, tenure, competitiveness. Email for data.
- **Thompson 2020 APSR** [verified] — sheriff partisanship × 287(g). Replication data has sheriff party by county.
- **Su 2025 AJPS** [verified] — sheriff election cycles and traffic fines.
- **ICE 287(g) agreements** (ice.gov/identify-and-arrest/287g) [verify URL] — sheriff participation. Directly relevant to the ICE paragraph; strong candidate for both adoption *and* rejection.
- **Vera Incarceration Trends** — county jail population (sheriff-run). [verify status]

## 4. Governance (place) — deprioritise

- ICMA MFOG is paywalled [verified].
- Substitutes: Tausanovitch & Warshaw 2014 replication data (cities > 20k) [verify]; de Benedictis-Kessner & Warshaw mayoral data; Ballotpedia top-100.
- The draft already doubts an effect. **Drop the five-form typology**; keep `incorporated` + `own_pd`; run T&W subsample only if asked.

## 5. Private-sector demand proxies

- **Retail / big-box:** you already pull OSM — add `shop=doityourself`, `shop=department_store`, `shop=supermarket`, `amenity=parking` counts. Overture Places is the free alternative. Home Depot's store list is public.
- **HOAs:** no national data. Clarke & Freedman 2019 (JUE) used ZTRAX — discontinued. ACS proxies: share built 1990+ (B25034), share single-family detached (B25024). State the limitation.
- **Data centers:** Data Center Map / Baxtel. Footnote unless Stone has a reason.

## 6. State level

- **NCSL ALPR state statutes** (already footnoted). Code `state_alpr_statute`, `retention_limit_days`, `private_use_restricted`. Enters a 3-level model, or justifies state FE.

## 7. The rejection dataset (bans / pauses)

- **Finding Flock tracker** — only 14 rows (Aug 2026) but a clean **coding scheme**: `place, state, decision_date, action ∈ {canceled, non-renewal, paused, rejected, deactivated}, reason, source`. Adopt it.
- **The Hill (Sept 2026)** — cancellations "grow"; Washington Examiner counts 23 states.
- **WPR (Sept 9, 2026)** — a dozen-plus Wisconsin cities in one week over data-resale. **After** the draft's Sept 5 NPR cite — cutoff date matters.
- **DeFlock "wins"**, EFF, LexisNexis for the systematic pass.
- Add fields: `vendor`, `n_cameras_osm_pre`, `council_vote_margin`, `trigger ∈ {ICE/CBP access, data resale, officer misuse, cost, court}`, `unit ∈ {city, county, school district, university}`.
- Model: among adopters, logit of any restriction on the same covariates + Trump share + turnout + county restriction. This is where politics should bite.

## 8. Crosswalks

- **ORI → FIPS place/county:** LEAIC 2012; CDE roster lat/lon → spatial join for post-2012 agencies.
- **GOVS ID → FIPS:** GID file in the CoG release.
- **Place → county:** TIGER; Stone uses centroid. Flag places that cross county lines.
- **Tract → place:** tracts don't nest in places. Centroid or largest-overlap; ~30–40% of tracts are in no place — that's `in_place = 0`, the sheriff is the police.

## 9. Order of operations

1. CoG 2022 → `place_police.csv` + refresh `county_sheriff.csv`. (~3 h. Biggest gap, one download.)
2. Kaplan + LEAIC → `place_crime.csv`, `county_crime.csv` with coverage + MVT. (~4 h.)
3. Sheriff institutions: elected, 287(g), CSLLEA sworn, LEMAS flag. (~3 h.)
4. Transparency-portal scrape → `agency_flock.csv`. (~4–6 h; parkable.)
5. GVA tract proxy. (~3 h; robustness only.)
6. Ban dataset — only if Stone isn't on it.
