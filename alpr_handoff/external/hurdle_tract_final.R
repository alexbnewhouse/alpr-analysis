# Hurdle model of ALPR camera adoption and intensity, US Census tracts.
#
#   Rscript external/hurdle_tract_final.R
#
# ---------------------------------------------------------------------------
# WHY glmmTMB AND NOT fixest OR pscl
#
# The second part of a hurdle is a ZERO-TRUNCATED count model. Fitting an
# ordinary negative binomial to the positive subsample (e.g. fenegbin on
# filter(d, y > 0)) is a misspecification, not an approximation: on this data
# it understates every slope by roughly 50% and puts theta out by a factor of
# five.
#
#   pscl::hurdle   correct truncated likelihood, cannot absorb 2,270 counties
#   fixest         absorbs counties, has no truncated-NB family
#   glmmTMB        truncated_nbinom2 AND county as a random intercept  <- used
#
# County enters as a random intercept rather than a fixed effect. That is the
# price of the correct likelihood at this scale. The fixed-effects logit is
# reported alongside Part 1 as a robustness check, where fixest can do it.
# ---------------------------------------------------------------------------

suppressMessages({
  library(arrow); library(dplyr); library(glmmTMB); library(fixest)
})

# ------------------------------------------------------------------ data ----
d <- read_parquet("external/data/model_frame_tract.parquet") %>%
  filter(
    !is.na(population), population > 0,
    !is.na(land_area_sqkm), land_area_sqkm > 0,
    !is.na(pop_density_sqkm), pop_density_sqkm > 0,
    !is.na(median_hh_income), !is.na(pct_below_poverty),
    !is.na(pct_black), !is.na(pct_hispanic), !is.na(pct_asian),
    !is.na(pct_renter_occupied), !is.na(median_age)
  ) %>%
  mutate(
    log_income  = log(median_hh_income),
    log_area    = log(land_area_sqkm),
    log_density = log(pop_density_sqkm),
    county      = factor(county_fips),
    any_camera  = as.integer(n_cameras > 0)
  )

cat(sprintf("estimation sample: %s tracts in %s counties (%.1f%% zero)\n",
            format(nrow(d), big.mark = ","),
            format(n_distinct(d$county), big.mark = ","),
            100 * mean(d$n_cameras == 0)))

# NOTE ON SCALE TERMS. log_pop is deliberately absent: log_pop = log_density +
# log_area exactly, so entering all three is perfectly collinear. {log_area,
# log_density} spans the same space. The quadratic captures the inverted-U in
# density found descriptively -- zeros are most common at BOTH extremes, so a
# linear density term averages two opposite tails into a misleading slope.
RHS <- ~ log_income + pct_below_poverty +
         pct_black + pct_hispanic + pct_asian +   # white alone = reference
         pct_renter_occupied + median_age +
         log_area + log_density + I(log_density^2)

f1 <- update(RHS, any_camera ~ . + (1 | county))
f2 <- update(RHS, n_cameras  ~ . + (1 | county))

# ------------------------------------------------ Part 1: adoption ----------
cat("\nfitting Part 1 (adoption, logit)...\n")
m_adopt <- glmmTMB(f1, data = d, family = binomial())

# ------------------------------------------------ Part 2: intensity ---------
cat("fitting Part 2 (intensity, zero-truncated NB)...\n")
m_intensity <- glmmTMB(update(RHS, n_cameras ~ . + (1 | county)),
                       data = filter(d, n_cameras > 0),
                       family = truncated_nbinom2)

cat("\n===== PART 1: ADOPTION (logit, county random intercept) =====\n")
print(summary(m_adopt))
cat("\n===== PART 2: INTENSITY (zero-truncated NB2, county random intercept) =====\n")
print(summary(m_intensity))

# --------------------------------------------- robustness: FE logit ---------
# Part 1 can be estimated with true county FIXED effects, which fixest does
# efficiently. Counties whose tracts are all-zero or all-positive drop out.
m_adopt_fe <- feglm(update(RHS, any_camera ~ . + 0 | county),
                    data = d, family = binomial(), cluster = ~county)
cat("\n===== ROBUSTNESS: Part 1 with county FIXED effects =====\n")
print(summary(m_adopt_fe))

saveRDS(list(adopt = m_adopt, intensity = m_intensity, adopt_fe = m_adopt_fe),
        "external/data/hurdle_tract_final.rds")
cat("\nsaved -> external/data/hurdle_tract_final.rds\n")
