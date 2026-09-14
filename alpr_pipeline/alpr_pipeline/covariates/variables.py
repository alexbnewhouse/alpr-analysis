"""Curated ACS variable definitions for political-science covariates.

Every column number below was verified against the live 2023 ACS 5-year
table-based summary files rather than assumed -- ACS renumbers variables between
table versions, and a silently shifted index produces plausible-looking garbage.

Rates are computed against the table's own universe (`_E001` unless noted),
not against total population, because ACS universes differ per table: B17001's
universe is "population for whom poverty status is determined", B25003's is
"occupied housing units", B23025's is the civilian labor force. Dividing any of
those by total population would be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Measure:
    """One output column, derived from one ACS table."""

    name: str
    table: str
    numerator: tuple[int, ...]
    denominator: int | None = None
    description: str = ""
    #: Multiply the ratio by this (100 => percent).
    scale: float = 100.0

    @property
    def is_ratio(self) -> bool:
        return self.denominator is not None

    def columns(self) -> set[str]:
        cols = {f"{self.table}_E{n:03d}" for n in self.numerator}
        if self.denominator is not None:
            cols.add(f"{self.table}_E{self.denominator:03d}")
        return cols


# Universe notes are from the ACS table shells.
MEASURES: list[Measure] = [
    # --- population and age
    Measure("pop_total", "B01003", (1,), None, "Total population", scale=1.0),
    Measure("median_age", "B01002", (1,), None, "Median age (years)", scale=1.0),

    # --- income and inequality
    Measure("median_hh_income", "B19013", (1,), None,
            "Median household income, inflation-adjusted dollars", scale=1.0),
    Measure("per_capita_income", "B19301", (1,), None,
            "Per capita income, inflation-adjusted dollars", scale=1.0),
    Measure("gini_index", "B19083", (1,), None,
            "Gini index of income inequality (0-1)", scale=1.0),

    # --- race and ethnicity (universe: total population)
    Measure("pct_white", "B02001", (2,), 1, "% White alone"),
    Measure("pct_black", "B02001", (3,), 1, "% Black or African American alone"),
    Measure("pct_amerindian", "B02001", (4,), 1,
            "% American Indian and Alaska Native alone"),
    Measure("pct_asian", "B02001", (5,), 1, "% Asian alone"),
    Measure("pct_two_or_more", "B02001", (8,), 1, "% Two or more races"),
    Measure("pct_hispanic", "B03003", (3,), 1, "% Hispanic or Latino (any race)"),

    # --- nativity (universe: total population)
    Measure("pct_foreign_born", "B05002", (13,), 1, "% Foreign born"),

    # --- poverty (universe: pop. for whom poverty status is determined)
    Measure("pct_below_poverty", "B17001", (2,), 1,
            "% below poverty level in the past 12 months"),

    # --- education (universe: population 25 years and over)
    Measure("pct_bachelors_plus", "B15003", (22, 23, 24, 25), 1,
            "% aged 25+ with a bachelor's degree or higher"),

    # --- employment (universe: civilian labor force, _E003)
    Measure("pct_unemployed", "B23025", (5,), 3,
            "% of civilian labor force unemployed"),

    # --- housing (universe: occupied housing units)
    Measure("pct_renter_occupied", "B25003", (3,), 1,
            "% of occupied housing units that are renter-occupied"),
    Measure("median_home_value", "B25077", (1,), None,
            "Median value of owner-occupied units, dollars", scale=1.0),
    Measure("median_gross_rent", "B25064", (1,), None,
            "Median gross rent, dollars", scale=1.0),
    # E003 = owner-occupied with no vehicle, E010 = renter-occupied with none.
    Measure("pct_no_vehicle", "B25044", (3, 10), 1,
            "% of occupied housing units with no vehicle available"),

    # --- commuting (universe: workers 16+); car dependence is plausibly
    # related to where plate readers are worth deploying.
    Measure("pct_drove_alone", "B08301", (3,), 1,
            "% of workers who drove alone to work"),
    Measure("pct_public_transit", "B08301", (10,), 1,
            "% of workers using public transportation"),
]


def tables_needed(measures: list[Measure] | None = None) -> dict[str, set[str]]:
    """Map each ACS table id to the set of columns any measure needs from it."""
    measures = measures or MEASURES
    out: dict[str, set[str]] = {}
    for m in measures:
        out.setdefault(m.table, set()).update(m.columns())
    return out


# --- Summary levels -------------------------------------------------------
#
# GEO_ID in the summary files is "<sumlevel><component>US<fips>", e.g.
# "1400000US08013012345". Keying on the 7-char prefix selects a level.

@dataclass(frozen=True)
class SummaryLevel:
    code: str
    name: str
    fips_length: int
    #: Column name for the joined GEOID on the camera table.
    geoid_column: str
    #: Cartographic boundary file basename at www2.census.gov.
    boundary_slug: str = ""
    notes: str = ""


SUMMARY_LEVELS: dict[str, SummaryLevel] = {
    "county": SummaryLevel(
        "0500000", "County", 5, "geoid_county", "county",
        "3,222 units. Most covariates are reliable here."),
    "place": SummaryLevel(
        "1600000", "Place (city/town)", 7, "geoid_place", "place",
        "32,325 units. Municipality-level; cameras outside any incorporated "
        "place get NULL."),
    "tract": SummaryLevel(
        "1400000", "Census tract", 11, "geoid_tract", "tract",
        "85,381 units. The recommended default: full table availability and "
        "usable margins of error."),
    "bg": SummaryLevel(
        "1500000", "Block group", 12, "geoid_bg", "bg",
        "242,296 units. Finest level published, but many detailed tables are "
        "NOT released at block group and margins of error are wide. Treat "
        "point estimates here as indicative, not precise."),
}

DEFAULT_LEVEL = "tract"
