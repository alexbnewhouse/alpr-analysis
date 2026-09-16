# Load the external-snapshot panels into R.
#   source("external/load_external.R")
library(arrow); library(dplyr)

EXT <- "external/data"
if (!dir.exists(EXT)) stop("run python external/build_external_panels.py first")

cameras_ext     <- read_parquet(file.path(EXT, "cameras_geocoded.parquet"))
panel_tract_ext <- read_parquet(file.path(EXT, "panel_geo_tract.parquet"))
panel_zcta_ext  <- read_parquet(file.path(EXT, "panel_geo_zcta.parquet"))
panel_place_ext <- read_parquet(file.path(EXT, "panel_geo_place.parquet"))
panel_cnty_ext  <- read_parquet(file.path(EXT, "panel_geo_county.parquet"))

# Tract nests in county -- this is the column that makes fixed effects possible.
panel_tract_ext <- panel_tract_ext %>% mutate(county_fips = substr(tract_geoid, 1, 5))

cat(sprintf("cameras_ext      %7d rows (%d Flock)\n",
            nrow(cameras_ext), sum(cameras_ext$is_flock)))
cat(sprintf("panel_tract_ext  %7d tracts in %d counties\n",
            nrow(panel_tract_ext), n_distinct(panel_tract_ext$county_fips)))
cat(sprintf("panel_zcta_ext   %7d\n", nrow(panel_zcta_ext)))
cat(sprintf("panel_place_ext  %7d\n", nrow(panel_place_ext)))
cat(sprintf("panel_cnty_ext   %7d\n", nrow(panel_cnty_ext)))

# GEOIDs are character and keep leading zeros. Never coerce to numeric.
