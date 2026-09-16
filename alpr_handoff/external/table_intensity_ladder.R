# Specification ladder for the INTENSITY margin (Part 2 of the hurdle).
#
#   Rscript external/table_intensity_ladder.R
#
# Estimated on the 38,417 tracts with at least one camera. Every column uses a
# ZERO-TRUNCATED negative binomial: the second margin of a hurdle is defined
# over the strictly positive integers, and fitting an untruncated NB to the
# positive subsample attenuates slopes by roughly half.
#
#   (1) Demographics only
#   (2) + scale and road exposure
#   (3) + land use
#   (4) + state fixed effects
#   (5) + county, via Mundlak      -- the specification we use
#
# Writes LaTeX to docs/table_intensity_ladder.tex.

library(arrow)
library(dplyr)
library(glmmTMB)
library(stargazer)

DEMOG    <- c("log_income", "pct_below_poverty", "pct_black", "pct_hispanic",
              "pct_asian", "pct_renter_occupied", "median_age")
EXPOSURE <- c("log_pop", "log_area", "ld_c_sq", "log_road_km", "has_arterial")
LANDUSE  <- c("employment_ratio", "pct_jobs_retail_food")
ALL_X    <- c(EXPOSURE, LANDUSE, DEMOG)

d <- read_parquet("external/data/model_frame_tract.parquet") %>%
  filter(population > 0, land_area_sqkm > 0, !is.na(median_hh_income)) %>%
  mutate(
    log_pop      = log(population),
    log_area     = log(land_area_sqkm),
    log_income   = log(median_hh_income),
    has_arterial = as.integer(road_km_arterial > 0),
    log_road_km  = ifelse(road_km_arterial > 0, log(road_km_arterial), 0),
    ld_c         = log(pop_density_sqkm) - mean(log(pop_density_sqkm), na.rm = TRUE),
    ld_c_sq      = ld_c^2,
    state_fips   = factor(substr(tract_geoid, 1, 2)),
    county       = factor(county_fips)
  ) %>%
  filter(if_all(all_of(ALL_X), ~ !is.na(.))) %>%
  filter(n_cameras > 0)                       # the Part 2 estimation sample

d <- d %>% group_by(county) %>%
  mutate(across(all_of(ALL_X), ~ mean(.x, na.rm = TRUE), .names = "cm_{.col}")) %>%
  ungroup()

cat(sprintf("N = %s camera-bearing tracts in %s counties\n",
            format(nrow(d), big.mark = ","),
            format(n_distinct(d$county), big.mark = ",")))

fmla <- function(terms) as.formula(paste("n_cameras ~", paste(terms, collapse = " + ")))
tnb  <- function(terms) glmmTMB(fmla(terms), data = d, family = truncated_nbinom2)

m1 <- tnb(DEMOG)
m2 <- tnb(c(DEMOG, EXPOSURE))
m3 <- tnb(c(DEMOG, EXPOSURE, LANDUSE))
m4 <- tnb(c(DEMOG, EXPOSURE, LANDUSE, "state_fips"))
m5 <- tnb(c(ALL_X, paste0("cm_", ALL_X), "(1|county)"))

# stargazer cannot read glmmTMB, so each column is rendered from a glm shell
# with the same right-hand side and its coefficients overridden.
shell <- function(terms) glm(fmla(terms), data = d, family = poisson())
sh <- list(shell(DEMOG), shell(c(DEMOG, EXPOSURE)),
           shell(c(DEMOG, EXPOSURE, LANDUSE)),
           shell(c(DEMOG, EXPOSURE, LANDUSE, "state_fips")),
           shell(c(ALL_X, paste0("cm_", ALL_X))))
fits <- list(m1, m2, m3, m4, m5)

grab <- function(fit, shl) {
  nm <- names(coef(shl))
  list(co = fixef(fit)$cond[nm], se = sqrt(diag(vcov(fit)$cond))[nm])
}
got   <- Map(grab, fits, sh)
coefs <- lapply(got, `[[`, "co")
ses   <- lapply(got, `[[`, "se")

aic_line   <- format(round(sapply(fits, AIC)), big.mark = ",", trim = TRUE)
theta_line <- sprintf("%.2f", sapply(fits, function(m) sigma(m)))

stargazer(
  sh, coef = coefs, se = ses,
  type = "latex", out = "docs/table_intensity_ladder.tex",
  title = "Intensity margin: how many ALPR cameras, given at least one?",
  label = "tab:intensity-ladder",
  dep.var.labels.include = FALSE,
  column.labels = c("Demog.", "+Expos.", "+Land use", "+State FE", "+Mundlak"),
  model.numbers = TRUE, dep.var.caption = "",
  omit = c("^cm_", "state_fips", "Constant"),
  covariate.labels = c(
    "Log population", "Log land area", "Log density squared (centred)",
    "Log arterial km", "Has arterial road",
    "Employment ratio", "Retail job share",
    "Log median HH income", "Poverty rate",
    "Share Black", "Share Hispanic", "Share Asian",
    "Share renter-occupied", "Median age"),
  order = c(EXPOSURE, LANDUSE, DEMOG),
  add.lines = list(
    c("State FE", "No", "No", "No", "Yes", "No"),
    c("County effects", "No", "No", "No", "No", "Mundlak"),
    c("County means", "No", "No", "No", "No", "Yes"),
    c("Dispersion $\\theta$", theta_line),
    c("AIC", aic_line)),
  keep.stat = "n",
  no.space = TRUE, digits = 3, font.size = "footnotesize",
  notes = "See notes below.", notes.align = "l"
)

NOTE <- paste(
  "Zero-truncated negative binomial coefficients, standard errors in parentheses.",
  "$^{*}$p$<$0.1; $^{**}$p$<$0.05; $^{***}$p$<$0.01.",
  "Estimated on tracts with at least one camera; all columns use the same sample.",
  "Column 5 is a county random intercept with the county mean of every covariate",
  "(Mundlak), which reproduces county fixed effects; its plain coefficients are",
  "within-county effects.",
  "County means and state dummies are estimated but not reported."
)

tex <- readLines("docs/table_intensity_ladder.tex")
tex <- tex[!grepl("See notes below", tex, fixed = TRUE)]
tex <- tex[!grepl("textit{Note:}", tex, fixed = TRUE)]
tex <- sub("\\begin{tabular}{@{\\extracolsep{5pt}}lccccc}",
           "\\setlength{\\tabcolsep}{3pt}\\begin{tabular}{@{}lccccc@{}}",
           tex, fixed = TRUE)
te <- grep("\\end{tabular}", tex, fixed = TRUE)[1]
tex <- append(tex,
  c("\\vspace{0.6em}", "\\begin{minipage}{\\textwidth}\\footnotesize",
    paste("\\textit{Notes.}", NOTE), "\\end{minipage}"), after = te)
writeLines(tex, "docs/table_intensity_ladder.tex")

cat("\nwrote docs/table_intensity_ladder.tex\n\n")
watch <- c("log_income", "pct_below_poverty", "pct_black", "employment_ratio")
print(round(sapply(coefs, function(cf) cf[watch]), 3))
