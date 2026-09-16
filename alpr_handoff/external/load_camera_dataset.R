# Camera-level dataset: one row per camera, covariates at every geographic scale.
#   source("external/load_camera_dataset.R")
library(arrow); library(dplyr)

cameras <- read_parquet("external/data/camera_dataset.parquet")

# GEOIDs stay character -- as numeric, every California code loses its leading zero.
stopifnot(is.character(cameras$tract_geoid) || inherits(cameras$tract_geoid, "character"))

cat(sprintf("%s cameras x %d columns\n", format(nrow(cameras), big.mark=","), ncol(cameras)))
cat(sprintf("  Flock: %s (%.1f%%)\n", format(sum(cameras$is_flock), big.mark=","),
            100*mean(cameras$is_flock)))

# Contextual columns are suffixed by scale. To grab one scale's block:
tract_vars  <- grep("_tract$",  names(cameras), value = TRUE)
place_vars  <- grep("_place$",  names(cameras), value = TRUE)
county_vars <- grep("_county$", names(cameras), value = TRUE)
zcta_vars   <- grep("_zcta$",   names(cameras), value = TRUE)

cat(sprintf("  contextual columns: tract %d, place %d, county %d, zcta %d\n",
            length(tract_vars), length(place_vars), length(county_vars), length(zcta_vars)))

# Example: the same construct at four scales for one camera
cat("\nSame camera, median household income at each scale:\n")
ex <- cameras %>% filter(!is.na(median_hh_income_place)) %>% slice(1)
cat(sprintf("  tract %s | place %s | county %s | zcta %s\n",
            format(ex$median_hh_income_tract, big.mark=","),
            format(ex$median_hh_income_place, big.mark=","),
            format(ex$median_hh_income_county, big.mark=","),
            format(ex$median_hh_income_zcta, big.mark=",")))

# Reminder: this file has no rows for camera-less areas. For "what predicts
# having any cameras", use external/data/model_frame_<level>.parquet instead.
