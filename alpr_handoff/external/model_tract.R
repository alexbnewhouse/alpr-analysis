# Tract-level count models for ALPR camera density.
#
#   Rscript external/model_tract.R
#
# Requires external/data/tract_model_frame.parquet
#   (python external/build_tract_model_frame.py)

library(arrow); library(dplyr); library(fixest)

d <- read_parquet("external/data/tract_model_frame.parquet")

# GEOIDs must stay character. Read as numeric, every California tract loses its
# leading zero and mis-joins silently.
stopifnot(is.character(d$tract_geoid), is.character(d$county_fips))

cat(sprintf("tracts: %s | with cameras: %s (%.1f%%) | with covariates: %s\n",
            format(nrow(d), big.mark=","),
            format(sum(d$has_camera), big.mark=","),
            100*mean(d$has_camera),
            format(sum(!is.na(d$population)), big.mark=",")))

# ---------------------------------------------------------------------------
# THE BLOCKER
# ---------------------------------------------------------------------------
# Covariates exist only for tracts that HAVE cameras. Dropping incomplete rows
# silently reduces this to the selected sample -- exactly the bias we are
# trying to avoid. Refuse to proceed rather than report a biased estimate.
complete_zero <- sum(!is.na(d$population) & !d$has_camera)
BLOCKED <- complete_zero < 0.5 * sum(!d$has_camera)

if (BLOCKED) {
  cat("\n---------------------------------------------------------------\n")
  cat("BLOCKED: cannot estimate yet.\n\n")
  cat(sprintf("Covariates are missing for %s of %s zero-camera tracts.\n",
              format(sum(!d$has_camera & is.na(d$population)), big.mark=","),
              format(sum(!d$has_camera), big.mark=",")))
  cat("Every tract that HAS covariates also HAS a camera, so the adoption\n")
  cat("outcome is constant in the estimable sample -- there is literally no\n")
  cat("variation to explain. Any model fit on this would be conditioning on\n")
  cat("the outcome.\n\n")
  cat("Fix:\n")
  cat("  export CENSUS_API_KEY=...   # https://api.census.gov/data/key_signup.html\n")
  cat("  .venv/bin/python -m flock_alpr covariates\n")
  cat("  # then join acs_tract.parquet onto the zero tracts and re-run\n")
  cat("---------------------------------------------------------------\n\n")
  cat("Specification that will run once covariates are complete:\n\n")
  cat("  Part 1 (adoption):  feglm(has_camera ~ X | county_fips,\n")
  cat("                            family=binomial, cluster=~county_fips)\n")
  cat("  Part 2 (intensity): fenegbin(n_cameras ~ X | county_fips,\n")
  cat("                               offset=~log_pop, cluster=~county_fips)\n\n")
  quit(save = "no", status = 0)
}

d <- d %>%
  mutate(
    log_income   = log(pmax(median_hh_income, 1)),
    log_pop      = log(pmax(population, 1)),
    state_fips   = substr(tract_geoid, 1, 2)
  )

fit_sample <- d %>% filter(!is.na(population), population > 0)

# ---------------------------------------------------------------------------
# Specification
# ---------------------------------------------------------------------------
# Negative binomial, not Poisson: variance/mean is ~5.4 in the full universe,
# so Poisson standard errors would be roughly sqrt(5.4) ~ 2.3x too small.
#
# offset(log_pop) makes the outcome a *rate* (cameras per person) rather than
# a count, so coefficients are not just recovering population size.
#
# | county_fips absorbs county fixed effects -- available because tracts nest
# inside counties. This is the single reason to prefer tract over ZCTA: it
# identifies from within-county variation, differencing out county-level
# policing budgets, state law, and contracting environments.
#
# cluster = ~county_fips because deployment is decided at agency level, so
# tracts within a county are not independent observations.

covars <- c("log_income", "pct_below_poverty", "pct_black", "pct_hispanic",
            "pct_bachelors_plus", "pct_unemployed", "pct_renter_occupied",
            "pct_no_vehicle", "median_age")

f_count <- as.formula(paste("n_cameras ~", paste(covars, collapse = " + "),
                            "| county_fips"))

cat("\n=== Part 1: adoption (any camera at all) ===\n")
m_logit <- feglm(
  as.formula(paste("has_camera ~", paste(covars, collapse = " + "), "| county_fips")),
  data = fit_sample, family = binomial(), cluster = ~county_fips
)
print(summary(m_logit))

cat("\n=== Part 2: intensity (how many, given >0) ===\n")
m_nb <- fenegbin(
  f_count, data = filter(fit_sample, has_camera),
  offset = ~log_pop, cluster = ~county_fips
)
print(summary(m_nb))

cat("\n=== Single-equation NB over the full universe ===\n")
m_full <- fenegbin(f_count, data = fit_sample, offset = ~log_pop,
                   cluster = ~county_fips)
print(summary(m_full))

# ---------------------------------------------------------------------------
# Robustness the referee will ask for
# ---------------------------------------------------------------------------
# 1. Re-run at county level. A result that only appears at one aggregation is
#    an artifact of the zoning, not a finding (MAUP).
# 2. Re-run excluding retail-operated cameras (n_retail): Lowe's and Home Depot
#    deploy nationally by corporate procurement, which has nothing to do with
#    local crime or politics, and retail siting correlates with income.
# 3. Re-run on n_flock rather than n_cameras to isolate the vendor of interest.
# 4. The outcome measures cameras VOLUNTEERS HAVE MAPPED, not cameras
#    installed. Mapping effort plausibly correlates with education and income,
#    so a positive income coefficient is partly a discovery artifact. Control
#    for it using the ohsome mapping-effort denominators, or state the bound.

cat("\nRobustness checks to run: see comments at the foot of this script.\n")
