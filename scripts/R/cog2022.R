# Functions for building police-spending covariates from the 2022 Census of
# Governments, Finance component, individual-unit public-use files.
#
# Layouts (from "2022 S&L Public Use Files Technical Documentation.pdf"):
#   Fin_PID_2022.txt          146-char fixed width, one row per government
#   2022FinEstDAT_*modp.txt    32-char fixed width, one row per (government, item)
#
# GOVS ID = FIPS state (2) + type (1) + FIPS county (3) + unit id (6).
# Type: 0 state, 1 county, 2 city, 3 township, 4 special district, 5 school.
# Amounts are in THOUSANDS of dollars. Absent item = zero for any government
# that appears in the finance file at all; governments with no records are NA.
# Item flags: R reported, I imputed, A analyst correction, S alternative
# source, M unknown, N not applicable.

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(stringr)
})

POLICE_ITEMS <- c(
  E62 = "police_current_E62_k",       # Police protection - current operations
  F62 = "police_construction_F62_k",  # Police protection - construction
  M62 = "police_ig_M62_k"             # Police protection - intergovernmental to local NEC
)

# ---- readers -----------------------------------------------------------------

read_pid <- function(path) {
  cols <- fwf_cols(
    govs_id       = c(1, 12),
    name          = c(13, 76),
    county_name   = c(77, 111),
    place_code    = c(112, 116),
    pop_cog       = c(117, 125),
    pop_year      = c(126, 127),
    enrollment    = c(128, 134),
    enroll_year   = c(135, 136),
    sd_function   = c(137, 138),
    school_level  = c(139, 140),
    fy_ending     = c(141, 144),
    survey_year   = c(145, 146)
  )
  pid <- read_fwf(path, cols,
                  col_types = cols_only(
                    govs_id = "c", name = "c", county_name = "c", place_code = "c",
                    pop_cog = "d", pop_year = "c", fy_ending = "c", survey_year = "c"
                  ),
                  trim_ws = TRUE, progress = FALSE)
  pid %>%
    mutate(
      state_fips  = str_sub(govs_id, 1, 2),
      gov_type    = str_sub(govs_id, 3, 3),
      county_fips = str_sub(govs_id, 4, 6),
      # readr trims the place field; special districts/schools have it blank.
      place_code  = if_else(is.na(place_code) | place_code == "", NA_character_,
                            str_pad(place_code, 5, pad = "0"))
    ) %>%
    select(govs_id, state_fips, gov_type, county_fips, name, county_name,
           place_code, pop_cog, pop_year, fy_ending, survey_year)
}

read_fin <- function(path) {
  cols <- fwf_cols(
    govs_id  = c(1, 12),
    item     = c(13, 15),
    amount_k = c(16, 27),
    year     = c(28, 31),
    flag     = c(32, 32)
  )
  read_fwf(path, cols,
           col_types = cols(govs_id = "c", item = "c", amount_k = "d",
                            year = "c", flag = "c"),
           trim_ws = TRUE, progress = FALSE)
}

# ---- build ---------------------------------------------------------------------

# One row per general-purpose government (county, city, township) with the
# three police items spread wide, their flags, and whether the unit has any
# finance record at all.
police_wide <- function(pid, fin) {
  gp <- pid %>% filter(gov_type %in% c("1", "2", "3"))
  in_file <- fin %>% distinct(govs_id) %>% mutate(in_fin_file = TRUE)

  pol <- fin %>%
    filter(item %in% names(POLICE_ITEMS)) %>%
    select(govs_id, item, amount_k, flag)

  amounts <- pol %>%
    select(govs_id, item, amount_k) %>%
    pivot_wider(names_from = item, values_from = amount_k)
  flags <- pol %>%
    select(govs_id, item, flag) %>%
    pivot_wider(names_from = item, values_from = flag,
                names_glue = "{tolower(item)}_flag")

  # make sure every police column exists even if an item is absent in a fixture
  for (it in names(POLICE_ITEMS)) {
    if (!it %in% names(amounts)) amounts[[it]] <- NA_real_
    fl <- paste0(tolower(it), "_flag")
    if (!fl %in% names(flags)) flags[[fl]] <- NA_character_
  }

  out <- gp %>%
    left_join(in_file, by = "govs_id") %>%
    left_join(amounts, by = "govs_id") %>%
    left_join(flags, by = "govs_id") %>%
    mutate(in_fin_file = coalesce(in_fin_file, FALSE))

  # absent item -> 0 if the unit is in the finance file, else NA;
  # negative amounts (rare accounting corrections) -> NA rather than a spurious value
  for (it in names(POLICE_ITEMS)) {
    out[[it]] <- if_else(out$in_fin_file & is.na(out[[it]]), 0, out[[it]])
    out[[it]] <- if_else(!is.na(out[[it]]) & out[[it]] < 0, NA_real_, out[[it]])
  }
  out <- out %>% rename(!!!setNames(names(POLICE_ITEMS), unname(POLICE_ITEMS)))
  add_per_capita(out)
}

add_per_capita <- function(w) {
  w %>% mutate(
    police_pc_dollars = if_else(!is.na(pop_cog) & pop_cog > 0,
                                police_current_E62_k * 1000 / pop_cog, NA_real_)
  )
}

# Split into the three deliverables and add the county roll-up.
split_by_level <- function(w) {
  common <- c("govs_id", "name", "county_name", "pop_cog", "pop_year", "fy_ending",
              "in_fin_file", unname(POLICE_ITEMS), "e62_flag", "f62_flag", "m62_flag",
              "police_pc_dollars")

  place <- w %>%
    filter(gov_type == "2") %>%
    mutate(place_geoid = paste0(state_fips, place_code),
           county_fips_primary = paste0(state_fips, county_fips)) %>%
    select(place_geoid, county_fips_primary, all_of(common))

  cousub <- w %>%
    filter(gov_type == "3") %>%
    mutate(cousub_geoid = paste0(state_fips, county_fips, place_code),
           county_fips_primary = paste0(state_fips, county_fips)) %>%
    select(cousub_geoid, county_fips_primary, all_of(common))

  # municipal + township police located in each county (by the county in the ID)
  muni <- w %>%
    filter(gov_type %in% c("2", "3")) %>%
    mutate(county_geoid = paste0(state_fips, county_fips)) %>%
    group_by(county_geoid) %>%
    summarise(
      muni_police_E62_k   = sum(police_current_E62_k, na.rm = TRUE),
      n_muni_govts        = n(),
      n_muni_with_police  = sum(!is.na(police_current_E62_k) & police_current_E62_k > 0),
      .groups = "drop"
    )

  county <- w %>%
    filter(gov_type == "1") %>%
    mutate(county_geoid = paste0(state_fips, county_fips)) %>%
    select(county_geoid, all_of(common)) %>%
    left_join(muni, by = "county_geoid") %>%
    mutate(
      muni_police_E62_k  = coalesce(muni_police_E62_k, 0),
      n_muni_govts       = coalesce(n_muni_govts, 0L),
      n_muni_with_police = coalesce(n_muni_with_police, 0L),
      county_share_police = if_else(
        !is.na(police_current_E62_k) & (police_current_E62_k + muni_police_E62_k) > 0,
        police_current_E62_k / (police_current_E62_k + muni_police_E62_k),
        NA_real_)
    )

  list(place = place, cousub = cousub, county = county)
}
