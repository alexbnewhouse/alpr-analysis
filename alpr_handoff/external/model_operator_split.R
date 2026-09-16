# Split the outcome by who operates the camera, rather than controlling for it.
#
# Operator is UNDEFINED for zero-camera tracts and is post-treatment for
# camera tracts, so it cannot be a right-hand-side control. Splitting the
# dependent variable is the valid way to ask the same question.
library(arrow); library(dplyr); library(fixest)

d <- read_parquet("external/data/tract_model_frame.parquet") %>%
  filter(!is.na(population), population > 0) %>%
  mutate(log_income = log(pmax(median_hh_income, 1)),
         log_pop    = log(pmax(population, 1)))

covars <- c("log_income", "pct_below_poverty", "pct_black", "pct_hispanic",
            "pct_bachelors_plus", "pct_unemployed", "pct_renter_occupied",
            "pct_no_vehicle", "median_age")
rhs <- paste(covars, collapse = " + ")

cat(sprintf("tracts: %s | any police-tagged: %s | any retail-tagged: %s\n\n",
            format(nrow(d), big.mark=","),
            format(sum(d$n_police > 0), big.mark=","),
            format(sum(d$n_retail > 0), big.mark=",")))

for (dv in c("n_police", "n_retail")) {
  cat(sprintf("=== DV: %s ===\n", dv))
  m <- fenegbin(as.formula(paste(dv, "~", rhs, "| county_fips")),
                data = d, offset = ~log_pop, cluster = ~county_fips)
  print(summary(m))
  cat("\n")
}

# Is operator-tagging itself predicted by the covariates? If so, the split
# models are estimated on a selected sample and must be read with that caveat.
cat("=== Selection check: is being operator-TAGGED predictable? ===\n")
cam <- d %>% filter(has_camera) %>%
  mutate(tagged = (n_police + n_retail) > 0)
m_sel <- feglm(as.formula(paste("tagged ~", rhs, "| county_fips")),
               data = cam, family = binomial(), cluster = ~county_fips)
print(summary(m_sel))
