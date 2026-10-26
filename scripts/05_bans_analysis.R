#!/usr/bin/env Rscript
# Tables and figure for the draft's "Banning of Flock Cameras" section.
#
# Run from the project root:   Rscript scripts/05_bans_analysis.R
#
# Inputs
#   data/bans/bans_quick.csv, place_decisions.csv, county_decisions.csv   (scripts/04_build_bans_register.py)
#   data/out/place_politics_governance.csv                                (scripts/03_place_politics_governance.py)
#   alpr_handoff/external/data/model_frame_place.parquet                  (Stone's handoff)
# Outputs
#   output/tables/tab_ban_counts.tex        decisions by action, level, reason, period, state
#   output/tables/tab_ban_descriptives.tex  places that acted vs adopters that did not vs all places
#   output/tables/tab_ban_models.tex        Firth logits: any restriction / ban / pause, + state-FE check
#   output/tables/tab_ban_models_robust.tex local-only, whole-program, high-confidence, Flock-only, adopters-only
#   output/tables/ban_model_ame.csv         1-SD average marginal effects behind the text
#   output/figs/fig_ban_timeline.pdf        monthly decisions, Jan 2025 - Sep 2026
#
# Place universe = the draft's: places with positive population and observed
# median household income (28,298), which reproduces Table 1's place column.

suppressPackageStartupMessages({
  library(arrow); library(dplyr); library(tidyr); library(readr); library(stringr)
  library(logistf); library(fixest); library(ggplot2)
})
dir.create("output/tables", recursive = TRUE, showWarnings = FALSE)
dir.create("output/figs", recursive = TRUE, showWarnings = FALSE)
CUTOFF <- "2026-09-30"

# ---- data ---------------------------------------------------------------------
quick  <- read_csv("data/bans/bans_quick.csv", col_types = cols(.default = col_character()))
pdec   <- read_csv("data/bans/place_decisions.csv", col_types = cols(.default = col_character()))
cdec   <- read_csv("data/bans/county_decisions.csv", col_types = cols(.default = col_character()))
polgov <- read_csv("data/out/place_politics_governance.csv",
                   col_types = cols(place_geoid = col_character(), trump_2020_method = col_character(),
                                    .default = col_double()))

p <- read_parquet("alpr_handoff/external/data/model_frame_place.parquet") %>%
  filter(population > 0, !is.na(median_hh_income)) %>%
  left_join(polgov, by = "place_geoid") %>%
  left_join(pdec %>% select(place_geoid, starts_with("dv_")), by = "place_geoid") %>%
  mutate(
    across(starts_with("dv_"), ~ coalesce(as.integer(.x), 0L)),
    state_fips   = substr(place_geoid, 1, 2),
    log_pop      = log(population),
    log_area     = log(land_area_sqkm),
    ld_c_sq      = (log(population / land_area_sqkm) - mean(log(population / land_area_sqkm)))^2,
    log_road_km  = if_else(road_km_arterial > 0, log(road_km_arterial), 0),
    log_income   = log(median_hh_income),
    log_cameras  = log1p(n_cameras),
    has_camera   = as.integer(has_camera), has_arterial = as.integer(has_arterial),
    county_restricted = as.integer(county_fips %in% cdec$county_fips[cdec$dv_any == "1"]))
stopifnot(nrow(p) == 28298)
outside <- setdiff(pdec$place_geoid, p$place_geoid)

# ---- table 1: counts ----------------------------------------------------------
ACT <- c(canceled = "Contract cancelled", not_renewed = "Not renewed", ordinance_ban = "Ordinance ban",
         replaced_vendor = "Cancelled, switched vendor", suspended = "Paused / suspended",
         declined_to_adopt = "Rejected (declined to adopt)")
RSN <- c(federal_immigration_access = "Federal / immigration access", privacy = "Privacy / surveillance",
         unauthorized_access = "Misuse or unauthorised sharing", cost = "Cost", efficacy = "Efficacy",
         other = "Other", none = "Not stated")
q <- quick %>% mutate(
  trigger = if_else(is.na(trigger) | trigger == "", "none", trigger),
  month   = substr(decision_date, 1, 7),
  period  = case_when(is.na(month) | month == "" ~ "Date unknown",
                      month < "2025-01" ~ "Before 2025",
                      month < "2025-07" ~ "2025, Jan--Jun",
                      month < "2026-01" ~ "2025, Jul--Dec",
                      month < "2026-04" ~ "2026, Jan--Mar",
                      month < "2026-07" ~ "2026, Apr--Jun",
                      month == "2026-07" ~ "2026, July",
                      month == "2026-08" ~ "2026, August",
                      TRUE ~ "2026, September"))
PER <- c("Before 2025", "2025, Jan--Jun", "2025, Jul--Dec", "2026, Jan--Mar", "2026, Apr--Jun",
         "2026, July", "2026, August", "2026, September", "Date unknown")

fmt_int <- function(x) formatC(x, format = "d", big.mark = ",")
GEO <- c("place", "cousub", "county")  # cousub = New England towns and MI/OH/NJ/PA/NY townships
count_block <- function(d, var, labels) {
  d %>% count(.data[[var]], geo_type) %>%
    pivot_wider(names_from = geo_type, values_from = n, values_fill = 0) %>%
    { for (l in GEO) if (!l %in% names(.)) .[[l]] <- 0L; . } %>%
    mutate(total = place + cousub + county, lab = labels[.data[[var]]],
           ord = match(.data[[var]], names(labels))) %>%
    filter(!is.na(lab)) %>% arrange(ord)
}
row_tex <- function(b, n_tot) sprintf("\\quad %s & %s & %s & %s & %s & %.1f \\\\", b$lab, fmt_int(b$place),
                                      fmt_int(b$cousub), fmt_int(b$county), fmt_int(b$total), 100 * b$total / n_tot)
by_geo <- function(f) paste(sapply(GEO, function(g) f(q[q$geo_type == g, ])), collapse = " & ")
n_tot <- nrow(q)
st <- q %>% count(state, sort = TRUE)
top_st <- st %>% filter(n >= 8)
lines <- c(
  "% Generated by scripts/05_bans_analysis.R -- do not edit by hand.",
  "% Requires \\usepackage{booktabs,threeparttable}",
  "\\begin{table}[htbp]\\centering", "\\small",
  "\\begin{threeparttable}",
  "\\caption{Local decisions to pause, cancel, or reject ALPRs, through September 30, 2026}",
  "\\label{tab:ban-counts}",
  "\\begin{tabular}{@{}lrrrrr@{}}", "\\toprule",
  " & Places & Towns & Counties & Total & \\% \\\\", "\\midrule",
  "\\multicolumn{6}{@{}l}{\\textit{Action}} \\\\")
lines <- c(lines, row_tex(count_block(q, "action", ACT), n_tot),
           "\\addlinespace[2pt]", "\\multicolumn{6}{@{}l}{\\textit{Outcome as coded in the models}} \\\\",
           row_tex(q %>% mutate(dv = case_when(action == "suspended" ~ "pause",
                                               action == "declined_to_adopt" ~ "rejected", TRUE ~ "ban")) %>%
                     count_block("dv", c(ban = "Ban (cancelled, not renewed, banned)", pause = "Pause",
                                         rejected = "Rejected before adoption")), n_tot),
           row_tex(q %>% mutate(st_trig = if_else(state_triggered == "1", "yes", "no")) %>%
                     count_block("st_trig", c(yes = "Any of the above, following a state action")), n_tot),
           "\\addlinespace[2pt]", "\\multicolumn{6}{@{}l}{\\textit{Stated reason (primary)}} \\\\",
           row_tex(count_block(q, "trigger", RSN), n_tot),
           "\\addlinespace[2pt]", "\\multicolumn{6}{@{}l}{\\textit{Date of decision}} \\\\",
           row_tex(count_block(q, "period", setNames(PER, PER)), n_tot),
           "\\midrule",
           sprintf("Decisions & %s & %s & 100.0 \\\\", by_geo(function(d) fmt_int(nrow(d))), fmt_int(n_tot)),
           sprintf("Distinct jurisdictions & %s & %s & \\\\", by_geo(function(d) fmt_int(n_distinct(d$geoid))),
                   fmt_int(n_distinct(paste(q$geo_type, q$geoid)))),
           sprintf("States & %s & %s & \\\\", by_geo(function(d) n_distinct(d$state)), n_distinct(q$state)),
           "\\bottomrule", "\\end{tabular}",
           "\\begin{tablenotes}[flushleft]\\footnotesize",
           paste0("\\item \\textit{Notes.} One row per decision; a jurisdiction that paused and later cancelled appears twice, ",
                  "and the same decision reported by several sources appears once. \\textit{Towns} are New England towns and ",
                  "township governments (Census county subdivisions), which fall outside the Census place universe. ",
                  "Every decision was confirmed against a source document (council minutes, a government release, or local news) ",
                  "on October 26, 2026. Sources: the DeFlock ``wins'' register, a Nexis Uni search of local news, and a search for ",
                  "decisions those two had not yet recorded: every entry of two national trackers (deflocktheusa.com, whoapprovedthis.org) ",
                  "checked against local sources, plus state-by-state searches of local news and council records. ``Followed a state action'': decisions made because of a ",
                  "state law, order, or request --- chiefly Florida agencies acting on the state Department of Transportation's revocation of ",
                  "ALPR permits on state roads (August 31, 2026), Texas agencies acting on the governor's pause of state grant funding, and ",
                  "Washington agencies complying with SB 6002; also Vermont's ALPR statute and the Connecticut governor's pause request. ",
                  "Partial actions (only some cameras, only new installations, only state-road cameras) are counted as decisions. ",
                  "Reasons are as stated by the deciding body or reported in coverage; ``privacy'' includes general surveillance ",
                  "concerns. States with eight or more decisions: ",
                  paste(sprintf("%s (%d)", top_st$state, top_st$n), collapse = ", "), "."),
           "\\end{tablenotes}", "\\end{threeparttable}", "\\end{table}")
writeLines(lines, "output/tables/tab_ban_counts.tex")

# ---- table 2: descriptives ------------------------------------------------------
VARS <- list(
  "Outcome" = c("Any camera (0/1)" = "has_camera", "Cameras (count)" = "n_cameras"),
  "Demographic composition" = c("Share Black" = "pct_black", "Share Hispanic" = "pct_hispanic",
                                "Share Asian" = "pct_asian", "Share renter-occupied" = "pct_renter_occupied",
                                "Median age" = "median_age"),
  "Structural features" = c("Log population" = "log_pop", "Log land area" = "log_area",
                            "Log arterial road km" = "log_road_km", "Has arterial road (0/1)" = "has_arterial"),
  "Land use" = c("Employment ratio" = "employment_ratio", "Retail/food job share" = "pct_jobs_retail_food"),
  "Governance and police capacity" = c("Incorporated (0/1)" = "incorporated", "Own police department (0/1)" = "own_pd",
                                       "Log own police spending p.c." = "log_own_police_pc",
                                       "County also restricted (0/1)" = "county_restricted"),
  "Economic" = c("Log median household income" = "log_income", "Poverty rate" = "pct_below_poverty"),
  "Politics" = c("Trump 2020 vote share" = "trump_2020", "AIP ideology (cities $\\geq$ 20k)" = "aip_ideology"))
groups <- list(acted = p %>% filter(dv_any == 1),
               retained = p %>% filter(has_camera == 1, dv_any == 0),
               all = p)
ms <- function(d, v) {
  x <- d[[v]]; x <- x[is.finite(x)]
  dig <- if (v == "n_cameras" || v == "median_age") 2 else 3
  c(formatC(mean(x), format = "f", digits = dig), formatC(sd(x), format = "f", digits = dig))
}
dl <- c("% Generated by scripts/05_bans_analysis.R -- do not edit by hand.",
        "% Requires \\usepackage{booktabs,threeparttable}",
        "\\begin{table}[htbp]\\centering", "\\fontsize{9.5}{10.5}\\selectfont",
        "\\setlength{\\tabcolsep}{4pt}", "\\renewcommand{\\arraystretch}{0.9}",
        "\\begin{threeparttable}",
        "\\caption{Places that restricted ALPRs, compared with adopters that did not and with all places}",
        "\\label{tab:ban-descriptives}",
        "\\begin{tabular}{@{}l@{\\hspace{6pt}}rr@{\\hspace{12pt}}rr@{\\hspace{12pt}}rr@{}}", "\\toprule",
        " & \\multicolumn{2}{c}{\\shortstack{Restricted\\\\ \\strut}} & \\multicolumn{2}{c}{\\shortstack{Adopted, did\\\\not restrict}} & \\multicolumn{2}{c}{\\shortstack{All\\\\places}} \\\\",
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(l){6-7}",
        "Variable & Mean & SD & Mean & SD & Mean & SD \\\\", "\\midrule")
for (blk in names(VARS)) {
  dl <- c(dl, sprintf("\\multicolumn{7}{@{}l}{\\textit{%s}} \\\\", blk))
  for (lab in names(VARS[[blk]])) {
    v <- VARS[[blk]][[lab]]
    cells <- unlist(lapply(groups, ms, v = v))
    dl <- c(dl, sprintf("\\quad %s & %s \\\\", lab, paste(gsub("^-", "$-$", cells), collapse = " & ")))
  }
  dl <- c(dl, "\\addlinespace[2pt]")
}
dl <- c(head(dl, -1), "\\midrule",
        sprintf("Places & \\multicolumn{2}{c}{%s} & \\multicolumn{2}{c}{%s} & \\multicolumn{2}{c}{%s} \\\\",
                fmt_int(nrow(groups$acted)), fmt_int(nrow(groups$retained)), fmt_int(nrow(groups$all))),
        "\\bottomrule", "\\end{tabular}",
        "\\begin{tablenotes}[flushleft]\\fontsize{9}{10.5}\\selectfont",
        paste0("\\item \\textit{Notes.} Variables on the scale at which they enter the models, as in Table~\\ref{tab:descriptives}. ",
               "\\textit{Restricted} = any confirmed pause, cancellation, non-renewal, ban or rejection through September 30, 2026; ",
               "\\textit{Adopted, did not restrict} = places with at least one mapped camera and no such decision (the risk set for reversal). ",
               "Means use every unit where the variable is observed. Trump 2020 share sums 2020 precinct results reallocated to block groups ",
               "(contiguous US only) over the block groups inside each place; own police department and police spending are from the 2022 ",
               "Census of Governments. AIP ideology (higher = more conservative) covers cities above roughly 20,000 residents. ",
               sprintf("%d restricting places fall outside the place universe and are omitted.", length(outside))),
        "\\end{tablenotes}", "\\end{threeparttable}", "\\end{table}")
writeLines(dl, "output/tables/tab_ban_descriptives.tex")

# ---- table 3: models --------------------------------------------------------------
X <- c(has_camera = "Any camera (adoption)", log_cameras = "Log cameras (intensity)",
       log_pop = "Log population", log_income = "Log median HH income",
       pct_below_poverty = "Poverty rate", pct_black = "Share Black", pct_hispanic = "Share Hispanic",
       trump_2020 = "Trump 2020 vote share", incorporated = "Incorporated", own_pd = "Own police department",
       county_restricted = "County also restricted")
BLOCKS <- list("Camera exposure" = c("has_camera", "log_cameras"),
               "Structural and economic" = c("log_pop", "log_income", "pct_below_poverty"),
               "Demographic composition" = c("pct_black", "pct_hispanic"),
               "Politics" = "trump_2020",
               "Governance" = c("incorporated", "own_pd", "county_restricted"))
md <- p %>% filter(if_all(all_of(names(X)), ~ !is.na(.x)))
f_of <- function(y) reformulate(names(X), response = y)

fit_firth <- function(y, d = md, x = names(X)) {
  fm <- reformulate(x, response = y)
  m <- do.call(logistf, list(formula = fm, data = d, plconf = NULL))
  list(b = coef(m), se = sqrt(diag(vcov(m))), p = m$prob, n = nrow(d), ev = sum(d[[y]]),
       ll = m$loglik[["full"]], est = "Firth", states = "48 + DC")
}
fits <- lapply(c(any = "dv_any", ban = "dv_ban", pause = "dv_pause", local = "dv_any_local",
                 whole = "dv_any_whole", highconf = "dv_any_highconf", flock = "dv_any_flock"), fit_firth)
# adopters only: the risk set for reversal, so the adoption dummy drops out
fits$adopters <- fit_firth("dv_any", md %>% filter(has_camera == 1), setdiff(names(X), "has_camera"))
fe <- feglm(as.formula(paste("dv_any ~", paste(names(X), collapse = " + "), "| state_fips")),
            data = md, family = binomial, cluster = ~state_fips)
fe_fit <- list(b = coef(fe), se = se(fe), p = pvalue(fe), n = nobs(fe), ev = sum(fe$y), ll = as.numeric(logLik(fe)),
               est = "Logit", states = as.character(length(unique(md$state_fips[obs(fe)]))))

# 1-SD average marginal effects (observed-value approach, Hanmer & Kalkan 2013),
# predictions from the intercept-corrected Firth fit (FLIC) so rare-event
# probabilities are not inflated; binaries move 0 -> 1.
ame <- function(y) {
  fm <- f_of(y)
  m <- do.call(flic, list(formula = fm, data = md))
  mm <- model.matrix(fm, md)
  pr <- function(M) plogis(drop(M %*% coef(m)))
  bind_rows(lapply(names(X), function(v) {
    bin <- all(md[[v]] %in% c(0, 1))
    lo <- mm; hi <- mm
    if (bin) { lo[, v] <- 0; hi[, v] <- 1 } else hi[, v] <- hi[, v] + sd(md[[v]])
    tibble(outcome = y, term = v, label = X[[v]], change = if (bin) "0 to 1" else "+1 SD",
           sd = if (bin) NA_real_ else sd(md[[v]]),
           ame_pp = 100 * mean(pr(hi) - pr(lo)), base_rate_pct = 100 * mean(md[[y]]))
  }))
}
ames <- bind_rows(lapply(c("dv_any", "dv_ban", "dv_pause", "dv_any_local"), ame))
write_csv(ames, "output/tables/ban_model_ame.csv")

star <- function(p) ifelse(p < .01, "$^{***}$", ifelse(p < .05, "$^{**}$", ifelse(p < .1, "$^{*}$", "")))
num <- function(x) { d <- if (abs(x) < .01) 4 else 3; s <- formatC(x, format = "f", digits = d); sub("^-", "$-$", s) }
cell <- function(f, v) if (v %in% names(f$b)) sprintf("%s%s (%s)", num(f$b[[v]]), star(f$p[[v]]), num(f$se[[v]])) else "--"
row_of <- function(cols, f) paste(sapply(cols, f), collapse = " & ")

model_table <- function(cols, head1, head2, caption, label, note, file) {
  k <- length(cols)
  tl <- c("% Generated by scripts/05_bans_analysis.R -- do not edit by hand.",
          "\\begin{table}[htbp]\\centering", sprintf("\\caption{%s}", caption), sprintf("\\label{%s}", label),
          "\\footnotesize", "\\setlength{\\tabcolsep}{2pt}", "\\renewcommand{\\arraystretch}{1.15}",
          sprintf("\\begin{tabular*}{\\textwidth}{@{\\extracolsep{\\fill}}l%s@{}}", strrep("c", k)), "\\toprule",
          sprintf(" & %s \\\\", paste(head1, collapse = " & ")), sprintf(" & %s \\\\", paste(head2, collapse = " & ")),
          sprintf(" & %s \\\\", paste(sprintf("(%d)", seq_len(k)), collapse = " & ")), "\\midrule")
  for (blk in names(BLOCKS)) {
    tl <- c(tl, sprintf("\\addlinespace[2pt]\\multicolumn{%d}{@{}l}{\\textit{%s}} \\\\[1pt]", k + 1, blk))
    for (v in BLOCKS[[blk]]) tl <- c(tl, sprintf("\\quad %s & %s \\\\", X[[v]], row_of(cols, function(f) cell(f, v))))
  }
  c(tl, "\\midrule",
    sprintf("Constant & %s \\\\", row_of(cols, function(f) cell(f, "(Intercept)"))),
    sprintf("Places & %s \\\\", row_of(cols, function(f) fmt_int(f$n))),
    sprintf("Places that acted & %s \\\\", row_of(cols, function(f) fmt_int(f$ev))),
    sprintf("Estimator & %s \\\\", row_of(cols, function(f) f$est)),
    sprintf("States & %s \\\\", row_of(cols, function(f) f$states)),
    sprintf("Log-likelihood & %s \\\\", row_of(cols, function(f) sub("^-", "$-$", formatC(f$ll, format = "f", digits = 1, big.mark = ",")))),
    "\\bottomrule", "\\end{tabular*}", "", "\\vspace{0.5em}",
    "\\begin{minipage}{\\textwidth}\\footnotesize", note, "\\end{minipage}", "\\end{table}") %>%
    writeLines(file)
}
NOTE_COMMON <- paste0("\\textit{Notes.} Coefficients on the log-odds scale; standard errors in parentheses. ",
                      "$^{*}$p$<$0.1; $^{**}$p$<$0.05; $^{***}$p$<$0.01. ",
                      "Firth columns: penalised-likelihood logit (rare events), $p$-values from the penalised likelihood-ratio test. ",
                      "Universe: the place universe of Table~\\ref{tab:descriptives}, less places without 2020 vote data (Alaska, Hawaii, and places with no ",
                      "reallocated returns). Camera exposure enters as both margins of the hurdle: whether the place has any mapped camera, and how many. ",
                      "Descriptive associations, not causal effects.")
model_table(list(fits$any, fits$ban, fits$pause, fe_fit),
            c("Any", "", "", "Any,"), c("restriction", "Ban", "Pause", "state FE"),
            "Which places restricted ALPRs? Penalised logit, place level", "tab:ban-models",
            paste0(NOTE_COMMON, " \\textit{Any restriction} = any confirmed pause, ban, or rejection through September 30, 2026; ",
                   "\\textit{Ban} = cancelled, not renewed, banned by ordinance, or cancelled to switch vendor; \\textit{Pause} = suspended pending review. ",
                   "Column 4: ordinary logit with state fixed effects and state-clustered standard errors; states with no restricting place drop out. ",
                   "Robustness checks in Table~\\ref{tab:ban-models-robust}."),
            "output/tables/tab_ban_models.tex")
model_table(list(fits$local, fits$whole, fits$highconf, fits$flock, fits$adopters),
            c("Local", "Whole", "High-confidence", "Flock", "Adopters"), c("initiative", "program", "evidence", "only", "only"),
            "Which places restricted ALPRs? Robustness of the any-restriction model", "tab:ban-models-robust",
            paste0(NOTE_COMMON, " Outcome in every column: any restriction (Table~\\ref{tab:ban-models}, column 1), redefined as follows. ",
                   "(1) Drops decisions that followed a state law or order (Table~\\ref{tab:ban-counts}). ",
                   "(2) Drops partial actions --- those covering only some cameras, only new installations, or only cameras on state roads. ",
                   "(3) Keeps only decisions whose source states the action and date explicitly (high confidence). ",
                   "(4) Drops decisions about a vendor other than Flock Safety. ",
                   "(5) Restricts the sample to places with at least one mapped camera, the risk set for reversal."),
            "output/tables/tab_ban_models_robust.tex")

# ---- figure: timeline -------------------------------------------------------------
pre <- sum(q$month < "2025-01" & q$month != "", na.rm = TRUE)
months <- format(seq(as.Date("2025-01-01"), as.Date("2026-09-01"), by = "month"), "%Y-%m")
tl_d <- q %>% filter(month %in% months) %>%
  mutate(kind = factor(case_when(state_triggered == "1" ~ "Followed a state action",
                                 action == "suspended" ~ "Pause",
                                 action == "declined_to_adopt" ~ "Rejected before adoption",
                                 TRUE ~ "Ban (cancelled, not renewed, banned)"),
                       levels = c("Ban (cancelled, not renewed, banned)", "Pause", "Rejected before adoption",
                                  "Followed a state action"))) %>%
  count(month, kind) %>% complete(month = months, kind, fill = list(n = 0)) %>%
  mutate(date = as.Date(paste0(month, "-01")))
g <- ggplot(tl_d, aes(date, n, fill = kind)) +
  geom_col(width = 24, colour = "white", linewidth = 0.4) +
  scale_fill_manual(values = c("#2a78d6", "#eb6834", "#1baf7a", "#a3a29c"), name = NULL) +
  scale_x_date(breaks = seq(as.Date("2025-01-01"), as.Date("2026-09-01"), by = "3 months"),
               date_labels = "%b\n%Y", expand = expansion(add = 12)) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.05))) +
  labs(x = NULL, y = "Decisions per month") +
  guides(fill = guide_legend(nrow = 2, byrow = TRUE)) +
  theme_minimal(base_size = 10) +
  theme(panel.grid.major.x = element_blank(), panel.grid.minor = element_blank(),
        panel.grid.major.y = element_line(colour = "grey90", linewidth = 0.3),
        axis.text = element_text(colour = "grey30"), legend.position = "top",
        legend.justification = "left", legend.key.size = unit(9, "pt"),
        plot.background = element_rect(fill = "white", colour = NA))
ggsave("output/figs/fig_ban_timeline.pdf", g, width = 6.5, height = 3, device = cairo_pdf)
ggsave("output/figs/fig_ban_timeline.png", g, width = 6.5, height = 3, dpi = 200)
writeLines(c("% Generated by scripts/05_bans_analysis.R -- do not edit by hand.",
             "\\begin{figure}[htbp]\\centering",
             "\\includegraphics[width=\\textwidth]{figs/fig_ban_timeline.pdf}",
             "\\caption{Local decisions to pause, cancel, or reject ALPRs by month, January 2025--September 2026}",
             "\\label{fig:ban-timeline}",
             "\\begin{minipage}{\\textwidth}\\footnotesize",
             sprintf(paste0("\\textit{Notes.} Decisions by places, towns, and counties (Table~\\ref{tab:ban-counts}); ",
                            "%d decisions dated before 2025 and %d undated are not shown. Grey: decisions that followed a ",
                            "state law, order, or request (chiefly Florida's DOT permit revocation, the Texas grant-funding pause, and Washington's SB 6002), any outcome."),
                     pre, sum(is.na(q$month) | q$month == "")),
             "\\end{minipage}", "\\end{figure}"), "output/figs/fig_ban_timeline.tex")

# ---- console report -------------------------------------------------------------
cat(sprintf("decisions %d (municipal %d, counties %d); distinct Census places %d; pre-2025 decisions not in figure: %d\n",
            n_tot, sum(q$geo_type != "county"), sum(q$geo_type == "county"), n_distinct(q$geoid[q$geo_type == "place"]), pre))
cat(sprintf("place universe %d; model sample %d; events any/ban/pause %d/%d/%d; restricting places outside universe: %d\n",
            nrow(p), nrow(md), fits$any$ev, fits$ban$ev, fits$pause$ev, length(outside)))
print(ames %>% filter(outcome == "dv_any") %>% select(label, change, ame_pp, base_rate_pct), n = Inf)
