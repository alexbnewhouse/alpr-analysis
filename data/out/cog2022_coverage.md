# 2022 Census of Governments — police spending build: coverage report

Built 2026-09-13 from `Fin_PID_2022.txt` and `2022FinEstDAT_07152026modp.txt`. Amounts in thousands of FY2022 dollars.

## Units and coverage

| Level | Governments (PID) | In finance file | E62 > 0 | E62 imputed (flag I) | E62 reported (flag R) | Total E62 (millions) |
|---|---|---|---|---|---|---|
| County (→ `county_sheriff_2022.csv`) | 3,029 | 3,029 | 2,885 (95.2%) | 750 (26.0% of E62>0) | 2,112 | $37,718 |
| City (→ `place_police_2022.csv`) | 19,401 | 19,357 | 13,747 (70.9%) | 3,251 (23.6% of E62>0) | 10,444 | $73,361 |
| Township (→ `cousub_police_2022.csv`) | 15,981 | 15,879 | 2,956 (18.5%) | 468 (15.8% of E62>0) | 2,484 | $5,402 |

Absent E62 for a government that is in the finance file is coded **0** (the file omits zero items; only 
347 explicit zero-amount records exist in 1,337,594 rows). Governments with no finance records at all are **NA**.

## E62 flag distribution (governments in the finance file)

| gov_type | A | I | R | S | (absent) |
|---|---|---|---|---|---|
| county | 1 |   750 |  2,112 | 22 |    144 |
| city | 4 | 3,251 | 10,444 | 49 |  5,609 |
| township | 0 |   468 |  2,484 |  4 | 12,923 |

## How to join

- `place_police_2022.csv` → TIGER **place** GEOID (state + 5-digit place FIPS). Census Designated Places have no government and will not match: that is a true zero of *municipal* police spending, but the county sheriff still polices them — use `county_sheriff_2022.csv` for those.
- `cousub_police_2022.csv` → TIGER **county subdivision** GEOID (state + county + 5-digit COUSUB). Townships/towns in the 12 strong-MCD states (CT, ME, MA, MI, MN, NH, NJ, NY, PA, RI, VT, WI) plus Midwest civil townships. Many New England towns also exist as places (or CDPs) in TIGER; join on name+state if needed, or spatially.
- `county_sheriff_2022.csv` → county GEOID. County E62 is essentially the sheriff's operating budget (plus any county police department, e.g. MD, VA, NY suburbs). 
  Only 3,029 county governments exist vs 3,144 county-equivalents: missing ones are Connecticut, Rhode Island, most of Massachusetts (no county governments), Virginia independent cities and consolidated city-counties (which appear as cities, e.g. Denver = place 0820000), and Alaska boroughs without governments.
- `county_share_police` = county E62 / (county E62 + E62 of every city and township whose GOVS ID places it in that county). Cities spanning counties are counted once, in their primary county.
- Per-capita uses the Census of Governments population field (`pop_cog`, year `pop_year`); prefer ACS population in the models for consistency with the other covariates.
- **Per-capita has a real fat tail.** The top values are company/resort towns with almost no residents and large police budgets — Bay Lake and Lake Buena Vista FL (Disney), Vernon and Industry CA (industrial), Black Hawk CO (casinos). Log it or winsorize at the 99th percentile; do not drop them — they are exactly the parking-lot places the paper is about.
- One negative reported E62 (Mount Olivet city, KY, −23) is coded NA; all other amounts are ≥ 0.

## Sanity checks (thousands of $)

| Unit | Name | E62 |
|---|---|---|
| `county_geoid = 08013` | BOULDER COUNTY | 84,444 |
| `place_geoid = 0807850` | BOULDER CITY | 38,527 |
| `place_geoid = 0820000` | DENVER CITY AND COUNTY | 253,250 |
| `place_geoid = 0604758` | BEAUMONT CITY | 13,250 |
| `cousub_geoid = 2502109175` | BROOKLINE TOWN | 15,725 |

Expected: Boulder County ≈ 84,444; Boulder city ≈ 38,527; Denver ≈ 253,250; Beaumont CA ≈ 13,250 (the draft's $225,900 / 2-yr Flock contract is ≈0.85% of one year's police ops); Brookline MA ≈ a two-digit thousand.

## Not in this file

- Sworn officer counts / FTE → 2022 Census of Governments **Employment** (ASPEP), separate download.
- Total expenditure for a police-share-of-budget measure → needs the full item-code aggregation; add if Stone wants it.
- Item G62 (other capital outlay) does not appear in the 2022 file; F62 is the only capital item.
