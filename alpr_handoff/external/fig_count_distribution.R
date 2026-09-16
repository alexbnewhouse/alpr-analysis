# Figure 1: observed camera-count distribution vs Poisson and negative binomial.
#
#   Rscript external/fig_count_distribution.R
#
# Outputs PDF (for LaTeX) and PNG to external/figures/.
# What this figure does and does not show:
#   DOES  - Poisson is untenable. It implies 22.9% zeros against 54.0% observed.
#   DOES NOT - justify a hurdle over a plain negative binomial. The marginal NB,
#   with theta free, matches the observed zero share almost exactly. The case for
#   the hurdle is (a) conceptual, adoption and intensity being distinct decisions,
#   and (b) that once covariates and county fixed effects enter, the CONDITIONAL
#   NB does under-predict zeros. Do not caption this figure as evidence for the
#   hurdle -- it is evidence against Poisson.

suppressMessages({
  library(arrow); library(dplyr); library(ggplot2); library(MASS)
})

OUT <- "external/figures"
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)

# Reference palette, slots 1 and 2 (validated adjacent pair).
COL_OBS  <- "#c9c8c2"   # neutral: observed data is the reference, not a series
COL_POIS <- "#eb6834"   # slot 2, orange
COL_NB   <- "#2a78d6"   # slot 1, blue
INK      <- "#0b0b0b"
INK2     <- "#52514e"

TOP <- 10   # top-code the tail

tract <- read_parquet("external/data/model_frame_tract.parquet")
y <- tract$n_cameras
y <- y[!is.na(y)]
N <- length(y)

# --- fitted marginal distributions -----------------------------------------
lambda <- mean(y)
nb     <- suppressWarnings(MASS::fitdistr(y, "negative binomial"))
size   <- nb$estimate[["size"]]
mu     <- nb$estimate[["mu"]]

k <- 0:TOP
obs_counts <- as.integer(table(factor(pmin(y, TOP), levels = k)))

# Top bin is cumulative, so the fitted values must be upper-tail masses too.
pois_p <- c(dpois(0:(TOP - 1), lambda), 1 - ppois(TOP - 1, lambda))
nb_p   <- c(dnbinom(0:(TOP - 1), size = size, mu = mu),
            1 - pnbinom(TOP - 1, size = size, mu = mu))

df <- data.frame(
  k        = k,
  observed = 100 * obs_counts / N,
  Poisson  = 100 * pois_p,
  NegBin   = 100 * nb_p
)

fitted_long <- df %>%
  tidyr::pivot_longer(c(Poisson, NegBin), names_to = "model", values_to = "pct") %>%
  mutate(model = factor(model, levels = c("Poisson", "NegBin"),
                        labels = c("Poisson", "Negative binomial")))

labs_k <- c(as.character(0:(TOP - 1)), paste0(TOP, "+"))

p <- ggplot(df, aes(x = factor(k))) +
  # observed: thin bars with a small gap between neighbours
  geom_col(aes(y = observed), fill = COL_OBS, width = 0.68) +
  # fitted overlays: 2px lines, >=8px markers, ringed against the surface
  geom_line(data = fitted_long,
            aes(y = pct, colour = model, group = model), linewidth = 0.7) +
  geom_point(data = fitted_long,
             aes(y = pct, colour = model), size = 2.6,
             shape = 21, fill = "white", stroke = 1.0) +
  # direct label only where the story is, never on every bar
  annotate("text", x = 1.28, y = df$observed[1] + 1.5,
           label = sprintf("%.1f%% of tracts have none", df$observed[1]),
           colour = INK, size = 3.3, fontface = "bold", hjust = 0) +
  # tie the annotation to the Poisson marker it describes
  annotate("segment", x = 1.12, xend = 2.35,
           y = df$Poisson[1], yend = df$Poisson[1] + 8,
           colour = INK2, linewidth = 0.3) +
  annotate("text", x = 2.42, y = df$Poisson[1] + 8.4,
           label = sprintf("Poisson implies only %.1f%%", df$Poisson[1]),
           colour = INK2, size = 3.0, hjust = 0) +
  scale_x_discrete(labels = labs_k, expand = expansion(add = c(0.75, 0.6))) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.08)),
                     labels = function(v) paste0(v, "%")) +
  scale_colour_manual(values = c("Poisson" = COL_POIS,
                                 "Negative binomial" = COL_NB), name = NULL) +
  labs(x = "ALPR cameras in tract",
       y = "Share of tracts",
       title = "Observed camera counts against fitted count distributions",
       subtitle = sprintf("US Census tracts (N = %s). Poisson understates the zero mass\nby %.0f percentage points; the negative binomial does not.",
                          format(N, big.mark = ","), df$observed[1] - df$Poisson[1])) +
  theme_minimal(base_size = 11) +
  theme(
    panel.grid.minor   = element_blank(),
    panel.grid.major.x = element_blank(),
    panel.grid.major.y = element_line(colour = "#e7e6e1", linewidth = 0.3),
    axis.title         = element_text(colour = INK2, size = 9.5),
    axis.text          = element_text(colour = INK2, size = 9),
    plot.title         = element_text(colour = INK, size = 12, face = "bold"),
    plot.subtitle      = element_text(colour = INK2, size = 9.5,
                                      margin = margin(b = 10)),
    legend.position       = "inside",
    legend.position.inside = c(0.80, 0.78),
    legend.background  = element_rect(fill = "white", colour = NA),
    legend.text        = element_text(colour = INK2, size = 9),
    legend.key.height  = unit(14, "pt")
  )

ggsave(file.path(OUT, "fig_count_distribution.pdf"), p,
       width = 6.5, height = 4.2, device = cairo_pdf)
ggsave(file.path(OUT, "fig_count_distribution.png"), p,
       width = 6.5, height = 4.2, dpi = 200)

cat(sprintf("observed zero %.1f%% | Poisson %.1f%% | NB %.1f%%\n",
            df$observed[1], df$Poisson[1], df$NegBin[1]))
cat(sprintf("NB fitted: size(theta) = %.3f, mu = %.3f\n", size, mu))
cat("wrote", file.path(OUT, "fig_count_distribution.pdf"), "and .png\n")
