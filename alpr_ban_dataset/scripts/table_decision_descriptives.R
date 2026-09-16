# Summary statistics for municipalities and counties that paused, cancelled
# or banned ALPRs, against those that adopted and did not.
#
#   Rscript external/table_decision_descriptives.R
#
# Panel A is the place-level register (external/source/alpr_decisions_merged.csv),
# Panel B the county register (alpr_decisions_counties.csv). The comparison
# group in each panel is the RISK SET -- units that adopted and could
# therefore have reversed -- not all units, because a place with no cameras
# has nothing to cancel.
#
# Writes docs/table_decision_descriptives.tex.

suppressMessages({library(arrow); library(dplyr); library(readr)})

reg <- read_csv("external/source/alpr_decisions_merged.csv",
                col_types = cols(.default = col_character()))
cty_reg <- read_csv("external/source/alpr_decisions_counties.csv",
                    col_types = cols(.default = col_character()))

# ------------------------------------------------------------- places ----
p <- read_parquet("external/data/model_frame_place.parquet") %>%
  filter(n_cameras > 0) %>%                       # the risk set
  mutate(
    decided       = as.integer(place_geoid %in% reg$place_geoid),
    trump         = coalesce(trump_share_local, place_trump_aip),
    pop_1k        = population / 1000,
    income_1k     = median_hh_income / 1000,
    pct_black_100 = 100 * pct_black,
    pct_hisp_100  = 100 * pct_hispanic,
    pov_100       = 100 * pct_below_poverty,
    trump_100     = 100 * trump,
    emp_ratio     = employment_ratio,
    road_km       = road_km_arterial,
    prop_rate     = 1000 * property_crime_place / population)

PVARS <- c(
  "Population (000s)"          = "pop_1k",
  "ALPR cameras"               = "n_cameras",
  "Arterial road (km)"         = "road_km",
  "Employment ratio"           = "emp_ratio",
  "Median HH income (000s)"    = "income_1k",
  "Below poverty (\\%)"        = "pov_100",
  "Share Black (\\%)"          = "pct_black_100",
  "Share Hispanic (\\%)"       = "pct_hisp_100",
  "Trump 2020 share (\\%)"     = "trump_100",
  "AIP ideology"               = "place_ideology",
  "Property crime / 1{,}000"   = "prop_rate",
  "Has own police dept"        = "own_pd_i",
  "Incorporated"               = "incorporated_i",
  "County tier exists"         = "county_has_sheriff",
  "County also decided"        = "county_decided",
  "Mayor-council form"         = "gov_mayor_council",
  "At-large seats"             = "gov_at_large",
  "Has initiative"             = "gov_initiative")

p <- p %>% mutate(own_pd_i = as.integer(coalesce(n_police_agencies, 0L) > 0),
                  incorporated_i = as.integer(incorporated))

# ----------------------------------------------------------- counties ----
cty_reg2 <- cty_reg %>% mutate(cname = sub(",.*$", "", cityState))
cc <- read_parquet("external/data/model_frame_county.parquet") %>%
  filter(n_cameras > 0) %>%
  mutate(decided       = as.integer(county_decided == 1),
         pop_1k        = population / 1000,
         income_1k     = median_hh_income / 1000,
         pct_black_100 = 100 * pct_black,
         trump_100     = 100 * trump_share,
         pov_100       = 100 * pct_below_poverty,
         emp_ratio     = employment_ratio,
         road_km       = road_km_arterial,
         viol_rate     = 1000 * violent_crime_county / population,
         prop_rate     = 1000 * property_crime_county / population)

CVARS <- c(
  "Population (000s)"          = "pop_1k",
  "ALPR cameras"               = "n_cameras",
  "Arterial road (km)"         = "road_km",
  "Employment ratio"           = "emp_ratio",
  "Median HH income (000s)"    = "income_1k",
  "Below poverty (\\%)"        = "pov_100",
  "Share Black (\\%)"          = "pct_black_100",
  "Trump 2020 share (\\%)"     = "trump_100",
  "AIP ideology"               = "county_ideology",
  "Violent crime / 1{,}000"    = "viol_rate",
  "Property crime / 1{,}000"   = "prop_rate",
  "Sheriff agencies"           = "n_sheriff_agencies")

cell <- function(x) {
  x <- x[is.finite(x)]
  if (!length(x)) return(c("--", "--"))
  m <- mean(x); s <- sd(x)
  f <- function(v) if (abs(v) >= 1000) formatC(v, format = "d", big.mark = ",")
                   else sprintf("%.2f", v)
  c(f(m), paste0("(", f(s), ")"))
}

panel <- function(d, vars, label) {
  a <- d %>% filter(decided == 1); b <- d %>% filter(decided == 0)
  out <- c(sprintf("\\multicolumn{6}{@{}l}{\\textit{%s}} \\\\[2pt]", label))
  for (i in seq_along(vars)) {
    v <- vars[[i]]; nm <- names(vars)[i]
    if (!v %in% names(d)) next
    ca <- cell(a[[v]]); cb <- cell(b[[v]])
    xa <- a[[v]][is.finite(a[[v]])]; xb <- b[[v]][is.finite(b[[v]])]
    dif <- if (length(xa) && length(xb)) sprintf("%+.2f", mean(xa) - mean(xb)) else "--"
    out <- c(out, sprintf("%s & %s & %s & %s & %s & %s \\\\",
                          nm, ca[1], ca[2], cb[1], cb[2], dif))
  }
  c(out, sprintf("\\addlinespace Units & \\multicolumn{2}{c}{%s} & \\multicolumn{2}{c}{%s} & \\\\",
                 format(nrow(a), big.mark = ","), format(nrow(b), big.mark = ",")))
}

tex <- c(
"% Summary statistics for units that paused, cancelled or banned ALPRs.",
"% Requires: \\usepackage{booktabs, array}",
"\\begin{table}[htbp]", "\\centering\\footnotesize",
"\\caption{Who pauses or cancels ALPR programmes? Summary statistics}",
"\\label{tab:decision_descriptives}",
"\\setlength{\\tabcolsep}{4pt}",
"\\begin{tabular}{@{}lrrrrr@{}}", "\\toprule",
" & \\multicolumn{2}{c}{\\textbf{Paused / cancelled}} & \\multicolumn{2}{c}{\\textbf{Retained}} & \\\\",
"\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}",
" & Mean & (SD) & Mean & (SD) & Diff. \\\\", "\\midrule",
panel(p, PVARS, "Panel A. Municipalities"),
"\\addlinespace",
panel(cc, CVARS, "Panel B. Counties"),
"\\bottomrule", "\\end{tabular}",
"\\end{table}", "",
"\\noindent\\begin{minipage}{\\textwidth}\\footnotesize",
paste("\\textit{Notes.} The comparison group is the \\emph{risk set} --- units",
      "with at least one mapped ALPR camera, which are the only ones able to",
      "reverse course --- not all units. A place with no cameras has nothing",
      "to cancel, so including such places would inflate every difference."),
"",
paste("Municipal decisions are the union of two independently constructed",
      "sources: a Nexis Uni search of local news, and the DeFlock project's",
      "register. They overlap on only 15 of 151 places, and the overlap is",
      "size-graded --- median population 61,000 in both sources against",
      "34,000 in news alone and 18,000 in DeFlock alone --- so either source",
      "used by itself would understate the number of small municipalities",
      "that acted."),
"",
paste("\\textbf{The register is not yet verified.} No row has been confirmed",
      "against its underlying source document, and roughly a quarter of the",
      "news-derived entries are expected to be false positives on manual",
      "review. Differences are reported without significance tests for that",
      "reason; formal inference awaits verification."),
"",
paste("Governance variables cover cities above 20,000 population only",
      "(Tausanovitch and Warshaw), so those rows describe a large-city",
      "subsample. `County tier exists' indicates a county sheriff agency in",
      "the FBI roster: where none exists --- Connecticut, Massachusetts,",
      "Rhode Island, Alaska, Hawaii, DC and Delaware --- a county-level",
      "decision is structurally impossible rather than merely unobserved."),
"\\end{minipage}")

writeLines(tex, "docs/table_decision_descriptives.tex")
cat("wrote docs/table_decision_descriptives.tex\n")
cat(sprintf("  places: %d decided of %d in risk set\n", sum(p$decided), nrow(p)))
cat(sprintf("  counties: %d decided of %d in risk set\n", sum(cc$decided), nrow(cc)))
