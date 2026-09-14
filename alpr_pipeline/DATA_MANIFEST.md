# alpr_pipeline/data — manifest

Generated 2026-09-13 by `scripts/02_pipeline_manifest.py`. The directory itself is gitignored (≈1 GB); on Alex's machine it is a symlink to `~/flock_research/alpr_pipeline/data`.

## Files

| File | Size | Rows | Type |
|---|---|---|---|
| `acs2023_tract.csv` | 58 MB |  | csv |
| `acs2023_tract.parquet` | 16 MB | 85,381 | 55 cols |
| `alpr.sqlite` | 56 MB | snapshots=2, sqlite_sequence=1, cameras=125,247, observations=250,494 | sqlite |
| `alpr_cameras.csv` | 18 MB |  | csv |
| `alpr_cameras.geojson` | 57 MB |  | geojson |
| `alpr_cameras.parquet` | 5 MB | 125,247 | 41 cols |
| `alpr_cameras.xlsx` | 18 MB |  | xlsx |
| `alpr_cameras_us.csv` | 18 MB |  | csv |
| `alpr_cameras_us.geojson` | 57 MB |  | geojson |
| `alpr_cameras_us.parquet` | 5 MB | 124,623 | 41 cols |
| `alpr_cameras_us.xlsx` | 18 MB |  | xlsx |
| `alpr_us_full.sqlite` | 82 MB | snapshots=1, sqlite_sequence=1, cameras=125,827, observations=125,827 | sqlite |
| `alpr_worldwide.sqlite` | 52 KB | snapshots=0, sqlite_sequence=0, cameras=0, observations=0 | sqlite |
| `cameras_with_covariates_tract.csv` | 147 MB |  | csv |
| `cameras_with_covariates_tract.parquet` | 25 MB | 125,212 | 98 cols |
| `flock_cameras.csv` | 15 MB |  | csv |
| `flock_cameras.geojson` | 48 MB |  | geojson |
| `flock_cameras.parquet` | 4 MB | 103,934 | 41 cols |
| `flock_cameras_us.csv` | 15 MB |  | csv |
| `flock_cameras_us.parquet` | 4 MB | 103,865 | 41 cols |
| `flock_cameras_us.xlsx` | 15 MB |  | xlsx |
| `tract_panel.csv` | 61 MB |  | csv |
| `tract_panel.parquet` | 17 MB | 85,381 | 62 cols |

## Covariate cache (`data/cache/`)

| File | Size |
|---|---|
| `acs2023_b01002_tract.parquet` | 630 KB |
| `acs2023_b01003_tract.parquet` | 697 KB |
| `acs2023_b02001_tract.parquet` | 1 MB |
| `acs2023_b03003_tract.parquet` | 854 KB |
| `acs2023_b05002_tract.parquet` | 837 KB |
| `acs2023_b08301_tract.parquet` | 908 KB |
| `acs2023_b15003_tract.parquet` | 1 MB |
| `acs2023_b17001_tract.parquet` | 831 KB |
| `acs2023_b19013_tract.parquet` | 922 KB |
| `acs2023_b19083_tract.parquet` | 672 KB |
| `acs2023_b19301_tract.parquet` | 907 KB |
| `acs2023_b23025_tract.parquet` | 787 KB |
| `acs2023_b25003_tract.parquet` | 800 KB |
| `acs2023_b25044_tract.parquet` | 880 KB |
| `acs2023_b25064_tract.parquet` | 660 KB |
| `acs2023_b25077_tract.parquet` | 724 KB |
| `aip_county_ideology.tab` | 2 MB |
| `aip_place_ideology.tab` | 4 MB |
| `cb_2023_us_county_500k.zip` | 11 MB |
| `cb_2023_us_place_500k.zip` | 22 MB |
| `cb_2023_us_tract_500k.zip` | 55 MB |
| `medsl_countypres_2000_2016.csv` | 4 MB |
| `ne_admin1.geojson` | 39 MB |
| `ne_countries.geojson` | 13 MB |
| `ucr_offenses_known_monthly_2023.rds` | 8 MB |
| `vest_realloc_contig_us.zip` | 106 MB |
| `wikidata_labels.json` | 1 KB |
| `wikidata_rejected.json` | 168 B |

## `tract_panel.parquet` — the modelling table

- **85,381 tracts**; 38,947 with ≥1 camera (45.6%); 125,128 cameras, 104,547 Flock (83.6%).
- Camera count among adopters: median 1, mean 1.0, max 116.
- Columns:

  - `geoid` (str, 100% non-null)
  - `pop_total` (float64, 100% non-null)
  - `median_age` (float64, 99% non-null)
  - `median_hh_income` (float64, 98% non-null)
  - `per_capita_income` (float64, 99% non-null)
  - `gini_index` (float64, 99% non-null)
  - `pct_white` (float64, 99% non-null)
  - `pct_black` (float64, 99% non-null)
  - `pct_amerindian` (float64, 99% non-null)
  - `pct_asian` (float64, 99% non-null)
  - `pct_two_or_more` (float64, 99% non-null)
  - `pct_hispanic` (float64, 99% non-null)
  - `pct_foreign_born` (float64, 99% non-null)
  - `pct_below_poverty` (float64, 99% non-null)
  - `pct_bachelors_plus` (float64, 99% non-null)
  - `pct_unemployed` (float64, 99% non-null)
  - `pct_renter_occupied` (float64, 99% non-null)
  - `median_home_value` (float64, 96% non-null)
  - `median_gross_rent` (float64, 94% non-null)
  - `pct_no_vehicle` (float64, 99% non-null)
  - `pct_drove_alone` (float64, 99% non-null)
  - `pct_public_transit` (float64, 99% non-null)
  - `pres2020_dem` (float64, 97% non-null)
  - `pres2020_rep` (float64, 97% non-null)
  - `pres2020_other` (float64, 97% non-null)
  - `pres2020_total` (float64, 97% non-null)
  - `pres2020_dem_share` (float64, 96% non-null)
  - `survey_period` (str, 98% non-null)
  - `mrp_ideology` (float64, 98% non-null)
  - `mrp_ideology_se` (float64, 98% non-null)
  - `self_ideology` (float64, 98% non-null)
  - `demshare_pres` (float64, 98% non-null)
  - `sample_size` (float64, 98% non-null)
  - `actual_index_violent` (float64, 94% non-null)
  - `actual_index_property` (float64, 94% non-null)
  - `actual_index_total` (float64, 94% non-null)
  - `actual_murder` (float64, 94% non-null)
  - `actual_rape_total` (float64, 94% non-null)
  - `actual_robbery_total` (float64, 94% non-null)
  - `actual_assault_aggravated` (float64, 94% non-null)
  - `actual_burglary_total` (float64, 94% non-null)
  - `actual_theft_total` (float64, 94% non-null)
  - `actual_motor_vehicle_theft_total` (float64, 94% non-null)
  - `ucr_population` (float64, 94% non-null)
  - `ucr_agencies` (float64, 94% non-null)
  - `index_violent_per_100k` (float64, 94% non-null)
  - `index_property_per_100k` (float64, 94% non-null)
  - `index_total_per_100k` (float64, 94% non-null)
  - `murder_per_100k` (float64, 94% non-null)
  - `rape_total_per_100k` (float64, 94% non-null)
  - `robbery_total_per_100k` (float64, 94% non-null)
  - `assault_aggravated_per_100k` (float64, 94% non-null)
  - `burglary_total_per_100k` (float64, 94% non-null)
  - `theft_total_per_100k` (float64, 94% non-null)
  - `motor_vehicle_theft_total_per_100k` (float64, 94% non-null)
  - `camera_count` (int64, 100% non-null)
  - `flock_count` (int64, 100% non-null)
  - `n_mappers` (int64, 100% non-null)
  - `first_mapped` (str, 46% non-null)
  - `last_mapped` (str, 46% non-null)
  - `has_camera` (int64, 100% non-null)
  - `cameras_per_10k` (float64, 99% non-null)

## `alpr_cameras_us.parquet` — the US camera master

- **124,623 cameras**; `is_flock` = 103,865 (83.3%); `osm_type = way` (mistagged roads) = 18.
- Vendors: Flock Safety 103,864, (unknown) 6,748, Motorola Solutions 6,310, Genetec 2,843, Axis Communications 1,171, Leonardo/ELSAG 1,083, Rekor 603, Ubicquia 596.
- Operator tag present: 17.7% of rows (the draft's 'majority do not have this information').
- Editor metadata (`osm_user`) present in this *derived* export: 0.0%. The `overpass` harvest in `alpr_us_full.sqlite` (below) is where editor metadata lives.

## `alpr_us_full.sqlite` — the full Overpass harvest

- **125,827 cameras** with complete raw tags (`tags_json` on 125,827) and editor metadata (`osm_user` on 125,827; **20,210 distinct editors**). This is the source of `n_mappers` / `first_mapped` / `last_mapped` in the tract panel.
- Snapshots: overpass at 2026-08-04T15:45:29+00:00 (OSM base 2026-08-04T15:44:10Z).
