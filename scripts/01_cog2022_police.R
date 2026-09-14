#!/usr/bin/env Rscript
# Build police-spending covariates from the 2022 Census of Governments
# (Finance component, individual-unit public-use files).
#
# Run from the project root:   Rscript scripts/01_cog2022_police.R
#
# Inputs  (downloaded automatically if missing):
#   data/raw/cog2022/2022_Individual_Unit_files/Fin_PID_2022.txt
#   data/raw/cog2022/2022_Individual_Unit_files/2022FinEstDAT_*modp.txt
# Outputs:
#   data/out/place_police_2022.csv    one row per city-type government, keyed on 7-digit place GEOID
#   data/out/cousub_police_2022.csv   one row per township-type government, keyed on 10-digit county-subdivision GEOID
#   data/out/county_sheriff_2022.csv  one row per county government, keyed on 5-digit county GEOID
#   data/out/cog2022_coverage.md      coverage / imputation / sanity-check report
#
# Amounts are in thousands of dollars (FY2022). See scripts/R/cog2022.R for
# the layout and the absent-item-means-zero rule.

suppressPackageStartupMessages({ library(dplyr); library(readr); library(stringr) })
source("scripts/R/cog2022.R")

RAW_URL  <- "https://www2.census.gov/programs-surveys/gov-finances/tables/2022/2022_Individual_Unit_File.zip"
RAW_DIR  <- "data/raw/cog2022"
OUT_DIR  <- "data/out"
dir.create(RAW_DIR, recursive = TRUE, showWarnings = FALSE)
dir.create(OUT_DIR, recursive = TRUE, showWarnings = FALSE)

# ---- fetch -------------------------------------------------------------------
pid_path <- list.files(RAW_DIR, "Fin_PID_2022\\.txt$", recursive = TRUE, full.names = TRUE)
fin_path <- list.files(RAW_DIR, "^2022FinEstDAT_.*modp\\.txt$", recursive = TRUE, full.names = TRUE)
if (length(pid_path) == 0 || length(fin_path) == 0) {
  zip <- file.path(RAW_DIR, basename(RAW_URL))
  message("Downloading ", RAW_URL)
  download.file(RAW_URL, zip, mode = "wb", quiet = TRUE)
  unzip(zip, exdir = RAW_DIR)
  pid_path <- list.files(RAW_DIR, "Fin_PID_2022\\.txt$", recursive = TRUE, full.names = TRUE)
  fin_path <- list.files(RAW_DIR, "^2022FinEstDAT_.*modp\\.txt$", recursive = TRUE, full.names = TRUE)
}
stopifnot(length(pid_path) == 1, length(fin_path) == 1)
message("PID: ", pid_path, "\nFIN: ", fin_path)

# ---- build -------------------------------------------------------------------
pid <- read_pid(pid_path)
fin <- read_fin(fin_path)
w   <- police_wide(pid, fin)
out <- split_by_level(w)

write_csv(out$place,  file.path(OUT_DIR, "place_police_2022.csv"),   na = "")
write_csv(out$cousub, file.path(OUT_DIR, "cousub_police_2022.csv"),  na = "")
write_csv(out$county, file.path(OUT_DIR, "county_sheriff_2022.csv"), na = "")

# ---- coverage report ---------------------------------------------------------
pct <- function(x, d = 1) sprintf(paste0("%.", d, "f%%"), 100 * x)
fmt <- function(x) format(x, big.mark = ",")

lvl_summary <- function(df, label) {
  n      <- nrow(df)
  infile <- sum(df$in_fin_file)
  pos    <- sum(!is.na(df$police_current_E62_k) & df$police_current_E62_k > 0)
  imp    <- sum(df$e62_flag %in% "I")
  rep    <- sum(df$e62_flag %in% "R")
  tot    <- sum(df$police_current_E62_k, na.rm = TRUE)
  c(
    sprintf("| %s | %s | %s | %s (%s) | %s (%s of E62>0) | %s | $%s |",
            label, fmt(n), fmt(infile), fmt(pos), pct(pos / n),
            fmt(imp), pct(imp / max(pos, 1)), fmt(rep), fmt(round(tot / 1e3)))
  )
}

# Render a data frame as a GitHub-markdown table without pulling in knitr.
knitr_free_table <- function(df) {
  cells <- lapply(df, function(x) if (is.numeric(x)) fmt(x) else as.character(x))
  rows  <- do.call(paste, c(cells, sep = " | "))
  c(paste0("| ", paste(names(df), collapse = " | "), " |"),
    paste0("|", paste(rep("---", ncol(df)), collapse = "|"), "|"),
    paste0("| ", rows, " |"))
}

check <- function(df, key, val, col = "police_current_E62_k") {
  v <- df[[col]][df[[key]] == val]
  sprintf("| `%s = %s` | %s | %s |", key, val, df$name[df[[key]] == val][1],
          if (length(v)) fmt(v[1]) else "MISSING")
}

flag_tab <- w %>% filter(gov_type %in% c("1","2","3"), in_fin_file) %>%
  count(gov_type, e62_flag) %>%
  mutate(gov_type = recode(gov_type, `1` = "county", `2` = "city", `3` = "township"),
         e62_flag = coalesce(e62_flag, "(absent)")) %>%
  tidyr::pivot_wider(names_from = e62_flag, values_from = n, values_fill = 0)

report <- c(
  "# 2022 Census of Governments — police spending build: coverage report",
  "",
  sprintf("Built %s from `%s` and `%s`. Amounts in thousands of FY2022 dollars.",
          format(Sys.Date()), basename(pid_path), basename(fin_path)),
  "",
  "## Units and coverage",
  "",
  "| Level | Governments (PID) | In finance file | E62 > 0 | E62 imputed (flag I) | E62 reported (flag R) | Total E62 (millions) |",
  "|---|---|---|---|---|---|---|",
  lvl_summary(out$county, "County (→ `county_sheriff_2022.csv`)"),
  lvl_summary(out$place,  "City (→ `place_police_2022.csv`)"),
  lvl_summary(out$cousub, "Township (→ `cousub_police_2022.csv`)"),
  "",
  "Absent E62 for a government that is in the finance file is coded **0** (the file omits zero items; only ",
  sprintf("%s explicit zero-amount records exist in %s rows). Governments with no finance records at all are **NA**.",
          fmt(sum(fin$amount_k == 0)), fmt(nrow(fin))),
  "",
  "## E62 flag distribution (governments in the finance file)",
  "",
  knitr_free_table(flag_tab),
  "",
  "## How to join",
  "",
  "- `place_police_2022.csv` → TIGER **place** GEOID (state + 5-digit place FIPS). Census Designated Places have no government and will not match: that is a true zero of *municipal* police spending, but the county sheriff still polices them — use `county_sheriff_2022.csv` for those.",
  "- `cousub_police_2022.csv` → TIGER **county subdivision** GEOID (state + county + 5-digit COUSUB). Townships/towns in the 12 strong-MCD states (CT, ME, MA, MI, MN, NH, NJ, NY, PA, RI, VT, WI) plus Midwest civil townships. Many New England towns also exist as places (or CDPs) in TIGER; join on name+state if needed, or spatially.",
  "- `county_sheriff_2022.csv` → county GEOID. County E62 is essentially the sheriff's operating budget (plus any county police department, e.g. MD, VA, NY suburbs). ",
  sprintf("  Only %s county governments exist vs 3,144 county-equivalents: missing ones are Connecticut, Rhode Island, most of Massachusetts (no county governments), Virginia independent cities and consolidated city-counties (which appear as cities, e.g. Denver = place 0820000), and Alaska boroughs without governments.",
          fmt(nrow(out$county))),
  "- `county_share_police` = county E62 / (county E62 + E62 of every city and township whose GOVS ID places it in that county). Cities spanning counties are counted once, in their primary county.",
  "- Per-capita uses the Census of Governments population field (`pop_cog`, year `pop_year`); prefer ACS population in the models for consistency with the other covariates.",
  "- **Per-capita has a real fat tail.** The top values are company/resort towns with almost no residents and large police budgets — Bay Lake and Lake Buena Vista FL (Disney), Vernon and Industry CA (industrial), Black Hawk CO (casinos). Log it or winsorize at the 99th percentile; do not drop them — they are exactly the parking-lot places the paper is about.",
  "- One negative reported E62 (Mount Olivet city, KY, −23) is coded NA; all other amounts are ≥ 0.",
  "",
  "## Sanity checks (thousands of $)",
  "",
  "| Unit | Name | E62 |",
  "|---|---|---|",
  check(out$county, "county_geoid", "08013"),
  check(out$place,  "place_geoid",  "0807850"),
  check(out$place,  "place_geoid",  "0820000"),
  check(out$place,  "place_geoid",  "0604758"),
  check(out$cousub, "cousub_geoid", "2502109175"),
  "",
  "Expected: Boulder County ≈ 84,444; Boulder city ≈ 38,527; Denver ≈ 253,250; Beaumont CA ≈ 13,250 (the draft's $225,900 / 2-yr Flock contract is ≈0.85% of one year's police ops); Brookline MA ≈ a two-digit thousand.",
  "",
  "## Not in this file",
  "",
  "- Sworn officer counts / FTE → 2022 Census of Governments **Employment** (ASPEP), separate download.",
  "- Total expenditure for a police-share-of-budget measure → needs the full item-code aggregation; add if Stone wants it.",
  "- Item G62 (other capital outlay) does not appear in the 2022 file; F62 is the only capital item."
)

writeLines(report, file.path(OUT_DIR, "cog2022_coverage.md"))
message(paste(report, collapse = "\n"))
