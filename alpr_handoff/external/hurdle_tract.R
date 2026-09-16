# Two-part hurdle model of ALPR camera adoption and intensity, tract level.
#
#   Rscript external/hurdle_tract.R
#
# Part 1 (adoption)  : logit on whether a tract has any camera
# Part 2 (intensity) : negative binomial on how many, given >= 1
#
# Fitted with fixest rather than pscl::hurdle because pscl cannot absorb
# 2,000+ county fixed effects, and those fixed effects are the reason for
# choosing tract over ZIP in the first place -- they identify from
# within-county variation, differencing out state law, policing budgets and
# the local contracting environment.

suppressMessages({
  library(arrow)
  library(dplyr)
  library(fixest)
})

# ---------------------------------------------------------------- data ----
d <- read_parquet("external/data/model_frame_tract.parquet")

covars <- c("log_income", "pct_below_poverty", "pct_black", "pct_hispanic",
            "pct_bachelors_plus", "pct_unemployed", "pct_renter_occupied",
            "pct_no_vehicle", "median_age")

d <- d %>%
  filter(!is.na(population), population > 0, !is.na(median_hh_income)) %>%
  mutate(
    log_income = log(pmax(median_hh_income, 1)),
    log_pop    = log(population),          # offset: makes the outcome a RATE
    log_density = log(pmax(pop_density_sqkm, 0.01))
  ) %>%
  filter(if_all(all_of(covars), ~ !is.na(.)))

cat(sprintf("estimation sample: %s tracts, %.1f%% zeros\n",
            format(nrow(d), big.mark = ","), 100 * mean(d$n_cameras == 0)))

rhs <- paste(covars, collapse = " + ")

# ------------------------------------------------- Part 1: adoption -------
# Logit. No offset here: the outcome is binary, not a count.
# Clustered at county because deployment is decided by agencies, so tracts
# within a county are not independent draws.
m_adopt <- feglm(
  as.formula(paste("I(n_cameras > 0) ~", rhs, "| county_fips")),
  data    = d,
  family  = binomial(),
  cluster = ~county_fips
)

# ------------------------------------------------ Part 2: intensity -------
# Negative binomial on the positive counts only. offset(log_pop) turns the
# outcome into cameras-per-person, so coefficients are not just recovering
# population size. Poisson is not an option: variance/mean is ~5.4, so its
# standard errors would be roughly 2.3x too small.
m_intensity <- fenegbin(
  as.formula(paste("n_cameras ~", rhs, "| county_fips")),
  data    = filter(d, n_cameras > 0),
  offset  = ~log_pop,
  cluster = ~county_fips
)

cat("\n=== PART 1: ADOPTION ===\n");  print(summary(m_adopt))
cat("\n=== PART 2: INTENSITY ===\n"); print(summary(m_intensity))

# ------------------------------------------------------- robustness -------
# pct_renter_occupied is the strongest predictor in both parts and is very
# likely proxying urban density / road extent rather than tenure. Refit with
# density in to see whether it survives.
m_adopt_d <- feglm(
  as.formula(paste("I(n_cameras > 0) ~", rhs, "+ log_density | county_fips")),
  data = d, family = binomial(), cluster = ~county_fips
)
m_int_d <- fenegbin(
  as.formula(paste("n_cameras ~", rhs, "+ log_density | county_fips")),
  data = filter(d, n_cameras > 0), offset = ~log_pop, cluster = ~county_fips
)

cat("\n=== Robustness: adding log population density ===\n")
etable(m_adopt, m_adopt_d, m_intensity, m_int_d,
       headers = c("adopt", "adopt+dens", "intens", "intens+dens"),
       keep = c("renter", "income", "density", "poverty"))

saveRDS(list(adopt = m_adopt, intensity = m_intensity,
             adopt_density = m_adopt_d, intensity_density = m_int_d),
        "external/data/tract_hurdle_fe.rds")
