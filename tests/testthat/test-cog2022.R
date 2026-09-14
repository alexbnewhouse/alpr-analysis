# Tests for the 2022 Census of Governments police-spending build.
# Fixtures are tiny fixed-width strings in the exact public-use layouts
# (see data/raw/cog2022/.../techdoc.txt): PID = 146 chars, FinEst = 32 chars.

library(testthat)

# Walk up from wherever testthat put us until we find the project README.
here_root <- function(start = getwd()) {
  d <- normalizePath(start)
  for (i in 1:6) {
    if (file.exists(file.path(d, "README.md")) && dir.exists(file.path(d, "scripts"))) return(d)
    d <- dirname(d)
  }
  stop("project root not found")
}
source(file.path(here_root(), "scripts", "R", "cog2022.R"))

# ---- fixture helpers -------------------------------------------------------

pid_line <- function(id, name, county_name, place, pop, pop_yr = "22") {
  stopifnot(nchar(id) == 12)
  paste0(
    id,
    formatC(name, width = 64, flag = "-"),
    formatC(county_name, width = 35, flag = "-"),
    formatC(place, width = 5),
    formatC(as.integer(pop), width = 9, format = "d"),
    pop_yr,
    formatC("", width = 7), "  ",   # enrollment + year
    "  ", "  ",                     # function code, school level
    "0622", "22"                    # FY ending, survey year
  )
}

fin_line <- function(id, item, amount, flag = "R") {
  stopifnot(nchar(id) == 12, nchar(item) == 3)
  paste0(id, item, formatC(as.integer(amount), width = 12, format = "d"), "2022", flag)
}

write_fixture <- function(lines) {
  f <- tempfile(fileext = ".txt")
  writeLines(lines, f)
  f
}

# Boulder County (type 1), Boulder city (type 2), Brookline town (type 3),
# a CDP-less tiny city with no finance records at all, and a special district.
pid_fx <- write_fixture(c(
  pid_line("081013161308", "BOULDER COUNTY",  "Boulder",  "99013", 327171),
  pid_line("082013161337", "BOULDER CITY",    "Boulder",  "07850", 107645),
  pid_line("082013999999", "GHOST CITY",      "Boulder",  "12345",    500),
  pid_line("253021166534", "BROOKLINE TOWN",  "Norfolk",  "09175",  59022),
  pid_line("084013000001", "SOME WATER DIST", "Boulder",  "     ",      0)
))

fin_fx <- write_fixture(c(
  fin_line("081013161308", "E62",  84444, "R"),
  fin_line("081013161308", "T01",   1000, "R"),   # unrelated item
  fin_line("082013161337", "E62",  38527, "I"),
  fin_line("082013161337", "F62",    100, "R"),
  fin_line("253021166534", "E62",  12000, "R"),
  fin_line("253021166534", "M62",      5, "R"),
  fin_line("084013000001", "E62",    999, "R")    # special district police (excluded)
))

# ---- parsing ---------------------------------------------------------------

test_that("read_pid parses the 146-char layout into typed columns", {
  pid <- read_pid(pid_fx)
  expect_equal(nrow(pid), 5)
  b <- pid[pid$govs_id == "082013161337", ]
  expect_equal(b$state_fips, "08")
  expect_equal(b$gov_type, "2")
  expect_equal(b$county_fips, "013")
  expect_equal(b$name, "BOULDER CITY")
  expect_equal(b$county_name, "Boulder")
  expect_equal(b$place_code, "07850")
  expect_equal(b$pop_cog, 107645)
  expect_equal(b$pop_year, "22")
  sd <- pid[pid$gov_type == "4", ]
  expect_true(is.na(sd$place_code))
})

test_that("read_fin parses the 32-char layout and keeps the flag", {
  fin <- read_fin(fin_fx)
  expect_equal(nrow(fin), 7)
  r <- fin[fin$govs_id == "082013161337" & fin$item == "E62", ]
  expect_equal(r$amount_k, 38527)
  expect_equal(r$flag, "I")
  expect_equal(unique(fin$year), "2022")
})

# ---- police wide table -----------------------------------------------------

test_that("police_wide gives one row per general-purpose government with E62/F62/M62", {
  w <- police_wide(read_pid(pid_fx), read_fin(fin_fx))
  # special district excluded; state (type 0) would be too
  expect_setequal(w$govs_id, c("081013161308", "082013161337", "082013999999", "253021166534"))
  bc <- w[w$govs_id == "082013161337", ]
  expect_equal(bc$police_current_E62_k, 38527)
  expect_equal(bc$police_construction_F62_k, 100)
  expect_equal(bc$police_ig_M62_k, 0)          # absent item, unit in file -> 0
  expect_equal(bc$e62_flag, "I")
  expect_equal(bc$f62_flag, "R")
  expect_true(bc$in_fin_file)
})

test_that("a government with no finance records at all gets NA, not 0", {
  w <- police_wide(read_pid(pid_fx), read_fin(fin_fx))
  g <- w[w$govs_id == "082013999999", ]
  expect_false(g$in_fin_file)
  expect_true(is.na(g$police_current_E62_k))
  expect_true(is.na(g$e62_flag))
})

test_that("per-capita is dollars per resident and NA when population is zero or missing", {
  w <- police_wide(read_pid(pid_fx), read_fin(fin_fx))
  bc <- w[w$govs_id == "082013161337", ]
  expect_equal(bc$police_pc_dollars, 38527 * 1000 / 107645)
  # force a zero-pop case
  w2 <- w; w2$pop_cog[w2$govs_id == "082013161337"] <- 0
  expect_true(is.na(add_per_capita(w2)$police_pc_dollars[w2$govs_id == "082013161337"]))
})

# ---- GEOID construction ----------------------------------------------------

test_that("place GEOID is state + place code for cities; cousub GEOID is state+county+code for townships", {
  w <- police_wide(read_pid(pid_fx), read_fin(fin_fx))
  out <- split_by_level(w)
  expect_equal(out$place$place_geoid[out$place$govs_id == "082013161337"], "0807850")
  expect_equal(out$cousub$cousub_geoid[out$cousub$govs_id == "253021166534"], "2502109175")
  expect_equal(out$county$county_geoid[out$county$govs_id == "081013161308"], "08013")
  expect_false("081013161308" %in% out$place$govs_id)
})

# ---- county roll-up --------------------------------------------------------

test_that("county table carries municipal police totals and the county share", {
  w <- police_wide(read_pid(pid_fx), read_fin(fin_fx))
  out <- split_by_level(w)
  cty <- out$county[out$county$county_geoid == "08013", ]
  # municipalities located in county 013 of state 08: Boulder city (38527) + ghost city (NA -> ignored)
  expect_equal(cty$muni_police_E62_k, 38527)
  expect_equal(cty$n_muni_with_police, 1)
  expect_equal(cty$county_share_police, 84444 / (84444 + 38527))
})

test_that("negative police amounts become NA rather than a spurious value", {
  pid <- write_fixture(c(pid_line("212201100001", "MOUNT OLIVET CITY", "Robertson", "53616", 334)))
  fin <- write_fixture(c(fin_line("212201100001", "E62", -23, "R"),
                         fin_line("212201100001", "T01", 10, "R")))
  w <- police_wide(read_pid(pid), read_fin(fin))
  expect_true(w$in_fin_file)
  expect_true(is.na(w$police_current_E62_k))
  expect_equal(w$police_construction_F62_k, 0)
})
