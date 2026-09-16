# Descriptives for a count outcome with excess zeros.
#   source("external/descriptives_count.R"); count_desc(tract$n_cameras)

count_desc <- function(y, label = "outcome") {
  y  <- y[!is.na(y)]
  yp <- y[y > 0]

  cat(sprintf("\n=== %s: unconditional (N = %s) ===\n",
              label, format(length(y), big.mark = ",")))
  cat(sprintf("  Total                 %8s\n", format(sum(y), big.mark = ",")))
  cat(sprintf("  Mean                  %8.3f\n", mean(y)))
  cat(sprintf("  SD                    %8.3f\n", sd(y)))
  cat(sprintf("  Variance              %8.3f\n", var(y)))
  cat(sprintf("  Variance / mean       %8.2f   <- Poisson assumes 1\n", var(y)/mean(y)))
  cat(sprintf("  %% zero                %8.1f%%\n", 100*mean(y == 0)))
  cat(sprintf("  Median                %8.0f\n", median(y)))
  cat(sprintf("  P75 / P90 / P95 / P99 %4.0f %4.0f %4.0f %4.0f\n",
              quantile(y,.75), quantile(y,.90), quantile(y,.95), quantile(y,.99)))
  cat(sprintf("  Max                   %8.0f\n", max(y)))

  cat(sprintf("\n=== %s | y > 0  (Part 2 sample, N = %s) ===\n",
              label, format(length(yp), big.mark = ",")))
  cat(sprintf("  Mean                  %8.3f\n", mean(yp)))
  cat(sprintf("  SD                    %8.3f\n", sd(yp)))
  cat(sprintf("  Variance / mean       %8.2f\n", var(yp)/mean(yp)))
  cat(sprintf("  Median / P90 / Max    %4.0f %4.0f %4.0f\n",
              median(yp), quantile(yp,.90), max(yp)))

  cat("\n  observed zero share            ", sprintf("%5.1f%%\n", 100*mean(y == 0)))
  cat("  Poisson-implied zero share     ", sprintf("%5.1f%%\n", 100*exp(-mean(y))))

  invisible(data.frame(
    n = length(y), total = sum(y), mean = mean(y), sd = sd(y),
    var_mean = var(y)/mean(y), pct_zero = 100*mean(y == 0),
    median = median(y), p90 = quantile(y,.90), max = max(y),
    mean_pos = mean(yp), n_pos = length(yp)
  ))
}

# Frequency table, top-coded, for a paper table or figure.
count_freq <- function(y, top = 10) {
  y <- y[!is.na(y)]
  tab <- table(pmin(y, top))
  names(tab)[length(tab)] <- paste0(top, "+")
  data.frame(cameras = names(tab),
             tracts  = as.integer(tab),
             pct     = round(100*as.integer(tab)/length(y), 1))
}

if (sys.nframe() == 0) {
  suppressMessages({library(arrow); library(dplyr)})
  tract <- read_parquet("external/data/model_frame_tract.parquet")
  count_desc(tract$n_cameras, "n_cameras")
  count_desc(tract$n_flock,   "n_flock")
  cat("\n=== frequency table (n_cameras) ===\n")
  print(count_freq(tract$n_cameras), row.names = FALSE)
}
