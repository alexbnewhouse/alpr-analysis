# --------- Hurdle Models: ALPR cameras by Census tract -------------#
# What generates a camera in a tract?
# pscl estimates hurdle models. The formula is  count | zero , so the two
# margins can take different covariates.

library(arrow)
library(dplyr)
library(pscl)

# --------- Data -------------#
tracts <- read_parquet("external/data/model_frame_tract.parquet") %>%
  filter(population > 0, land_area_sqkm > 0, !is.na(median_hh_income)) %>%
  mutate(
    log_pop      = log(population),
    log_area     = log(land_area_sqkm),
    log_income   = log(median_hh_income),
    has_arterial = as.integer(road_km_arterial > 0),
    # 21% of tracts have no arterial road, so log() is undefined there.
    # has_arterial carries "any highway at all"; log_road_km carries how much.
    log_road_km  = ifelse(road_km_arterial > 0, log(road_km_arterial), 0),
    # Centred before squaring: uncentred this term has VIF 22, centred it is 1.8.
    ld_c         = log(pop_density_sqkm) - mean(log(pop_density_sqkm), na.rm = TRUE),
    ld_c_sq      = ld_c^2
  ) %>%
  filter(if_all(c(log_income, pct_below_poverty, pct_black, pct_hispanic,
                  pct_asian, pct_renter_occupied, median_age,
                  employment_ratio, pct_jobs_retail_food, ld_c_sq),
                ~ !is.na(.)))

cat(sprintf("N = %s tracts, %.1f%% zero\n",
            format(nrow(tracts), big.mark = ","), 100 * mean(tracts$n_cameras == 0)))

# --------- Formula -------------#
# Left of  |  is the count (intensity) margin, right is the zero (adoption)
# margin. Same covariates both sides here; drop terms from one side to let the
# margins differ.
f <- n_cameras ~
  log_pop + log_area + ld_c_sq + log_road_km + has_arterial +
  employment_ratio + pct_jobs_retail_food +
  log_income + pct_below_poverty +
  pct_black + pct_hispanic + pct_asian +
  pct_renter_occupied + median_age |
  log_pop + log_area + ld_c_sq + log_road_km + has_arterial +
  employment_ratio + pct_jobs_retail_food +
  log_income + pct_below_poverty +
  pct_black + pct_hispanic + pct_asian +
  pct_renter_occupied + median_age

# --------- Models -------------#
# first the Poisson hurdle
p.hurd <- hurdle(f, data = tracts, dist = "poisson",
                 link = "logit", zero.dist = "binomial")
summary(p.hurd)

# and the neg-bin hurdle
nb.hurd <- hurdle(f, data = tracts, dist = "negbin",
                  link = "logit", zero.dist = "binomial")
summary(nb.hurd)

# --------- Which one? -------------#
cat("\nAIC  Poisson:", round(AIC(p.hurd)), "  NegBin:", round(AIC(nb.hurd)), "\n")
cat("Theta:", round(nb.hurd$theta, 3),
    "-- far below the Poisson's implicit infinity, so the count margin is",
    "overdispersed and negbin is preferred.\n")

saveRDS(list(poisson = p.hurd, negbin = nb.hurd), "external/data/hurdle_pscl.rds")

# --------- Notes -------------#
# pscl cannot absorb the 2,270 county fixed effects, so these estimates use
# no geographic controls. State dummies are affordable and are a reasonable
# middle ground:
#
#   f_st <- update(f, . ~ . + factor(state_fips) | . + factor(state_fips))
#
# For true county fixed effects with the correct zero-truncated likelihood,
# see external/hurdle_tract_final.R (glmmTMB).
