# Count-model suite at tract level: Poisson / NB / ZIP / ZINB / hurdle.
suppressMessages({library(arrow); library(dplyr); library(fixest); library(pscl); library(MASS)})

d <- read_parquet("external/data/model_frame_tract.parquet") %>%
  filter(!is.na(population), population > 0, !is.na(median_hh_income)) %>%
  mutate(log_income = log(pmax(median_hh_income, 1)),
         log_pop    = log(population),
         log_area   = log(pmax(land_area_sqkm, 0.01)),
         state_fips = substr(tract_geoid, 1, 2))

covars <- c("log_income","pct_below_poverty","pct_black","pct_hispanic",
            "pct_bachelors_plus","pct_unemployed","pct_renter_occupied",
            "pct_no_vehicle","median_age")
d <- d %>% filter(if_all(all_of(covars), ~!is.na(.)))
rhs <- paste(covars, collapse=" + ")
cat(sprintf("estimation sample: %s tracts | %.1f%% zeros\n\n",
            format(nrow(d), big.mark=","), 100*mean(d$n_cameras==0)))

obs_zero <- sum(d$n_cameras == 0)

## ---- Models WITH county fixed effects (fixest) -------------------------
f <- as.formula(paste("n_cameras ~", rhs, "| county_fips"))
m_pois <- fepois  (f, data=d, offset=~log_pop, cluster=~county_fips)
m_nb   <- fenegbin(f, data=d, offset=~log_pop, cluster=~county_fips)

pred_zero_pois <- sum(dpois(0, fitted(m_pois)))
th <- m_nb$theta
pred_zero_nb   <- sum(dnbinom(0, size=th, mu=fitted(m_nb)))

cat("--- With county FE (fixest) ---\n")
cat(sprintf("  Poisson  AIC=%12.0f  predicted zeros=%6.0f\n", AIC(m_pois), pred_zero_pois))
cat(sprintf("  NegBin   AIC=%12.0f  predicted zeros=%6.0f  theta=%.3f\n",
            AIC(m_nb), pred_zero_nb, th))
cat(sprintf("  OBSERVED zeros                          %6d\n\n", obs_zero))

## ---- Zero-inflated / hurdle (pscl, NO high-dim FE possible) ------------
f2 <- as.formula(paste("n_cameras ~", rhs, "+ offset(log_pop)"))
m_zip  <- zeroinfl(f2, data=d, dist="poisson")
m_zinb <- zeroinfl(f2, data=d, dist="negbin")
m_hnb  <- hurdle  (f2, data=d, dist="negbin", zero.dist="binomial")

pz <- function(m) sum(predict(m, type="prob")[,1])
cat("--- Zero-inflated / hurdle (pscl, no county FE) ---\n")
cat(sprintf("  ZIP      AIC=%12.0f  predicted zeros=%6.0f\n", AIC(m_zip),  pz(m_zip)))
cat(sprintf("  ZINB     AIC=%12.0f  predicted zeros=%6.0f\n", AIC(m_zinb), pz(m_zinb)))
cat(sprintf("  HurdleNB AIC=%12.0f  predicted zeros=%6.0f\n", AIC(m_hnb),  pz(m_hnb)))
cat(sprintf("  OBSERVED zeros                          %6d\n\n", obs_zero))

## ---- Two-part hurdle that KEEPS the fixed effects ----------------------
cat("--- Two-part hurdle WITH county FE (recommended) ---\n")
m_adopt <- feglm(as.formula(paste("I(n_cameras>0) ~", rhs, "| county_fips")),
                 data=d, family=binomial(), cluster=~county_fips)
m_int   <- fenegbin(f, data=filter(d, n_cameras>0), offset=~log_pop,
                    cluster=~county_fips)
cat(sprintf("  Part 1 adoption : n=%s  pseudo-R2=%.3f\n",
            format(m_adopt$nobs, big.mark=","), fitstat(m_adopt,"pr2")$pr2))
cat(sprintf("  Part 2 intensity: n=%s  theta=%.3f\n",
            format(m_int$nobs, big.mark=","), m_int$theta))
saveRDS(list(adopt=m_adopt, intensity=m_int), "external/data/tract_hurdle_fe.rds")
