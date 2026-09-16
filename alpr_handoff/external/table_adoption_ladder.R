# Specification ladder for the ADOPTION margin (Part 1 of the hurdle).
#
#   Rscript external/table_adoption_ladder.R
#
# Five columns, each adding one layer of control, so a reader can watch the
# demographic coefficients move as exposure, land use and geography enter:
#
#   (1) Demographics only          -- the naive specification
#   (2) + scale and road exposure  -- opportunity for a camera to exist
#   (3) + land use                 -- commercial vs residential character
#   (4) + state fixed effects      -- coarse geography
#   (5) + county, via Mundlak      -- the specification we use
#
# Writes LaTeX to docs/table_adoption_ladder.tex.

library(arrow)
library(dplyr)
library(glmmTMB)
library(stargazer)

DEMOG    <- c("log_income", "pct_below_poverty", "pct_black", "pct_hispanic",
              "pct_asian", "pct_renter_occupied", "median_age")
EXPOSURE <- c("log_pop", "log_area", "ld_c_sq", "log_road_km", "has_arterial")
LANDUSE  <- c("employment_ratio", "pct_jobs_retail_food")
ALL_X    <- c(EXPOSURE, LANDUSE, DEMOG)

# ---------------------------------------------------------------- data ----
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
    state_fips   = substr(tract_geoid, 1, 2),
    county       = factor(county_fips),
    any_camera   = as.integer(n_cameras > 0)
  ) %>%
  filter(if_all(all_of(ALL_X), ~ !is.na(.)))

# Same estimation sample in every column, so differences are specification
# and not sample composition.
cat(sprintf("N = %s tracts in %s counties\n",
            format(nrow(d), big.mark = ","),
            format(n_distinct(d$county), big.mark = ",")))

d <- d %>% group_by(county) %>%
  mutate(across(all_of(ALL_X), ~ mean(.x, na.rm = TRUE), .names = "cm_{.col}")) %>%
  ungroup()

fmla <- function(terms) as.formula(paste("any_camera ~", paste(terms, collapse = " + ")))

# ---------------------------------------------------------------- models ---
m1 <- glm(fmla(DEMOG),                            data = d, family = binomial())
m2 <- glm(fmla(c(DEMOG, EXPOSURE)),               data = d, family = binomial())
m3 <- glm(fmla(c(DEMOG, EXPOSURE, LANDUSE)),      data = d, family = binomial())
m4 <- glm(fmla(c(DEMOG, EXPOSURE, LANDUSE, "factor(state_fips)")),
                                                  data = d, family = binomial())

cm_terms <- paste0("cm_", ALL_X)
m5 <- glmmTMB(fmla(c(ALL_X, cm_terms, "(1|county)")), data = d, family = binomial())

# stargazer does not know glmmTMB, so column 5 is rendered from a glm shell
# with the same right-hand side, its coefficients and standard errors
# overridden with the fitted glmmTMB values.
m5_shell <- glm(fmla(c(ALL_X, cm_terms)), data = d, family = binomial())
co5 <- fixef(m5)$cond
se5 <- sqrt(diag(vcov(m5)$cond))
nm  <- names(coef(m5_shell))
co5 <- co5[nm]; se5 <- se5[nm]

models <- list(m1, m2, m3, m4, m5_shell)
aic_line <- format(round(c(AIC(m1), AIC(m2), AIC(m3), AIC(m4), AIC(m5))),
                   big.mark = ",", trim = TRUE)
coefs  <- list(coef(m1), coef(m2), coef(m3), coef(m4), co5)
ses    <- list(summary(m1)$coefficients[, 2], summary(m2)$coefficients[, 2],
               summary(m3)$coefficients[, 2], summary(m4)$coefficients[, 2], se5)

# ---------------------------------------------------------------- table ----
stargazer(
  models,
  coef = coefs, se = ses,
  type = "latex", out = "docs/table_adoption_ladder.tex",
  title = "Adoption margin: does a tract contain any ALPR camera?",
  label = "tab:adoption-ladder",
  # Columns are built with fmla(c(DEMOG, EXPOSURE, ...)); stargazer deparses
  # those calls and uses them as per-column dependent-variable labels, which
  # puts 158 characters of literal R code in the header and blows the table
  # out to ~800pt. column.labels already identifies each column, so suppress
  # the dependent-variable row entirely.
  dep.var.labels.include = FALSE,
  # Short labels leave headroom: the header row is the binding constraint on
  # table width, and these keep it near 300pt against a 470pt text block, so
  # another column can be added later without the table overflowing.
  column.labels = c("Demog.", "+Expos.", "+Land use", "+State FE", "+Mundlak"),
  model.numbers = TRUE, dep.var.caption = "",
  omit = c("^cm_", "factor\\(state_fips\\)", "Constant"),
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
    # AIC is supplied by hand: column 5 is rendered from a glm shell, so
    # stargazer would otherwise report the SHELL's AIC, not the fitted model's.
    c("AIC", aic_line)),
  keep.stat = "n",
  no.space = TRUE, digits = 3, font.size = "footnotesize",
  # Keep this SHORT. stargazer puts notes in an unbreakable \multicolumn row
  # inside the tabular, so a long note sets the width of the whole table --
  # a 316-character note forced ~1327pt against a 469pt text block. The full
  # note goes below the tabular instead, where it wraps.
  notes = "See notes below.", notes.align = "l"
)

# --------- Make it fit the page -------------#
# stargazer emits notes as \multicolumn{5}{l}{...}: one unbreakable line inside
# the tabular. A long note therefore sets the width of the whole table -- here
# it forced ~1327pt against a 469pt text block. Two changes fix that:
#   1. move the notes OUT of the tabular, into a wrapping minipage below it,
#      so they cannot influence column widths at all;
#   2. wrap the tabular in \resizebox as a guard against future label changes.
NOTE <- paste(
  "Logit coefficients, standard errors in parentheses.",
  "$^{*}$p$<$0.1; $^{**}$p$<$0.05; $^{***}$p$<$0.01.",
  "All columns use the same estimation sample.",
  "Column 5 is a county random intercept with the county mean of every",
  "covariate (Mundlak), which reproduces county fixed effects; its plain",
  "coefficients are within-county effects.",
  "County means and state dummies are estimated but not reported."
)

tex <- readLines("docs/table_adoption_ladder.tex")

# Drop stargazer's own note rows entirely; the real note goes below the tabular.
tex <- tex[!grepl("See notes below", tex, fixed = TRUE)]
tex <- tex[!grepl("textit{Note:}", tex, fixed = TRUE)]

# Compress the inter-column space. stargazer's default is \extracolsep{5pt}
# plus the document's \tabcolsep on both sides of every column -- with six
# columns that is most of the excess width. 1pt padding is enough to keep the
# numbers legibly separated.
tex <- sub("\\begin{tabular}{@{\\extracolsep{5pt}}lccccc}",
           "\\setlength{\\tabcolsep}{3pt}\\begin{tabular}{@{}lccccc@{}}",
           tex, fixed = TRUE)

# Notes below the tabular, inside the float, wrapped to the text width.
te <- grep("\\end{tabular}", tex, fixed = TRUE)[1]
tex <- append(tex,
  c("\\vspace{0.6em}",
    "\\begin{minipage}{\\textwidth}\\footnotesize",
    paste("\\textit{Notes.}", NOTE),
    "\\end{minipage}"),
  after = te)

writeLines(tex, "docs/table_adoption_ladder.tex")

cat("\nwrote docs/table_adoption_ladder.tex\n\n")

# What the ladder shows, printed for convenience.
watch <- c("log_income", "pct_below_poverty", "pct_black", "pct_asian")
cmp <- sapply(list(m1 = coef(m1), m2 = coef(m2), m3 = coef(m3),
                   m4 = coef(m4), m5 = co5),
              function(cf) cf[watch])
cat("How the demographic coefficients move across the ladder:\n")
print(round(cmp, 3))
