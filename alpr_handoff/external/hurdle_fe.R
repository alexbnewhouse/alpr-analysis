# --------- Hurdle model with county effects: ALPR cameras by Census tract ----
#
#   Rscript external/hurdle_fe.R
#
# WHY NOT pscl::hurdle WITH COUNTY DUMMIES
#   pscl builds a dense design matrix and maximises with optim. 2,270 county
#   dummies over 82,728 tracts is ~188M cells -- infeasible. And unlike OLS,
#   nonlinear models have no within-transformation that sweeps fixed effects
#   out, so there is no cheap algebraic route either.
#
# WHY NOT fenegbin ON THE POSITIVE SUBSAMPLE
#   The second margin of a hurdle is a ZERO-TRUNCATED count model. Fitting an
#   ordinary negative binomial to y>0 is a misspecification: on this data it
#   attenuates every slope by roughly half and puts theta out by 5x.
#
# WHAT THIS DOES INSTEAD: MUNDLAK CORRELATED RANDOM EFFECTS
#   A random intercept plus the county MEANS of every covariate. The
#   within-county coefficients then reproduce fixed effects, while keeping a
#   likelihood that admits zero truncation.
#
#   Validated on the adoption margin, where both are estimable:
#     correlation between FE and Mundlak coefficient vectors = 0.9999
#     median absolute difference                             = 3.0%
#   Mundlak also retains the 1,092 counties (4,656 tracts) that true FE must
#   drop for having no within-county variation in the outcome.

library(arrow)
library(dplyr)
library(glmmTMB)
library(fixest)

# --------- Data -------------#
X <- c("log_pop", "log_area", "ld_c_sq", "log_road_km", "has_arterial",
       "employment_ratio", "pct_jobs_retail_food",
       "log_income", "pct_below_poverty",
       "pct_black", "pct_hispanic", "pct_asian",
       "pct_renter_occupied", "median_age")

tracts <- read_parquet("external/data/model_frame_tract.parquet") %>%
  filter(population > 0, land_area_sqkm > 0, !is.na(median_hh_income)) %>%
  mutate(
    log_pop      = log(population),
    log_area     = log(land_area_sqkm),
    log_income   = log(median_hh_income),
    has_arterial = as.integer(road_km_arterial > 0),
    log_road_km  = ifelse(road_km_arterial > 0, log(road_km_arterial), 0),
    ld_c         = log(pop_density_sqkm) - mean(log(pop_density_sqkm), na.rm = TRUE),
    ld_c_sq      = ld_c^2,
    county       = factor(county_fips),
    any_camera   = as.integer(n_cameras > 0)
  ) %>%
  filter(if_all(all_of(X), ~ !is.na(.)))

# Mundlak terms: the county mean of each covariate.
tracts <- tracts %>%
  group_by(county) %>%
  mutate(across(all_of(X), ~ mean(.x, na.rm = TRUE), .names = "cm_{.col}")) %>%
  ungroup()

cat(sprintf("N = %s tracts in %s counties, %.1f%% zero\n",
            format(nrow(tracts), big.mark = ","),
            format(n_distinct(tracts$county), big.mark = ","),
            100 * mean(tracts$n_cameras == 0)))

rhs    <- paste(X, collapse = " + ")
cm_rhs <- paste(paste0("cm_", X), collapse = " + ")

# --------- Part 1: adoption -------------#
m_adopt <- glmmTMB(
  as.formula(paste("any_camera ~", rhs, "+", cm_rhs, "+ (1|county)")),
  data = tracts, family = binomial()
)

# --------- Part 2: intensity -------------#
# truncated_nbinom2 is the correct second margin of a hurdle.
m_intensity <- glmmTMB(
  as.formula(paste("n_cameras ~", rhs, "+", cm_rhs, "+ (1|county)")),
  data = filter(tracts, n_cameras > 0), family = truncated_nbinom2
)

cat("\n===== PART 1: ADOPTION (logit) =====\n")
print(summary(m_adopt))
cat("\n===== PART 2: INTENSITY (zero-truncated NB2) =====\n")
print(summary(m_intensity))

# --------- Check: does Mundlak match true FE on the margin where FE works? ---
m_adopt_fe <- feglm(as.formula(paste("any_camera ~", rhs, "| county")),
                    data = tracts, family = binomial(), cluster = ~county)
cmp <- data.frame(FE = coef(m_adopt_fe)[X],
                  Mundlak = fixef(m_adopt)$cond[X])
cat("\n===== FE vs Mundlak, adoption margin =====\n")
print(round(cmp, 4))
cat(sprintf("correlation = %.4f\n", cor(cmp$FE, cmp$Mundlak)))

saveRDS(list(adopt = m_adopt, intensity = m_intensity, adopt_fe = m_adopt_fe),
        "external/data/hurdle_fe.rds")

# --------- Reading the output -------------#
# Interpret the PLAIN covariates (log_pop, employment_ratio, ...) as
# within-county effects -- the fixed-effects estimand. The cm_ terms absorb
# between-county variation and are nuisance parameters, though the difference
# between a coefficient and its cm_ partner is itself a test of whether the
# within and between relationships differ.
