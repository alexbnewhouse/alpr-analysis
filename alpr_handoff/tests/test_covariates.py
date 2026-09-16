import pandas as pd
import pytest

from flock_alpr import covariates


def test_require_key_names_signup_url(monkeypatch):
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="key_signup"):
        covariates.require_key(
            "CENSUS_API_KEY", "https://api.census.gov/data/key_signup.html"
        )


def test_require_key_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("CENSUS_API_KEY", "abc123")
    assert covariates.require_key("CENSUS_API_KEY", "https://x") == "abc123"


def test_parse_acs_maps_codes_to_friendly_names():
    payload = (b'[["NAME","B19013_001E","B01003_001E","zip code tabulation area"],'
               b'["ZCTA5 27601","54321","18000","27601"]]')
    df = covariates.parse_acs(payload, "zcta")
    assert df.iloc[0]["median_hh_income"] == 54321
    assert df.iloc[0]["population"] == 18000
    assert df.iloc[0]["zcta"] == "27601"


def test_parse_acs_treats_census_sentinel_as_null():
    payload = (b'[["NAME","B19013_001E","zip code tabulation area"],'
               b'["ZCTA5 00001","-666666666","00001"]]')
    df = covariates.parse_acs(payload, "zcta")
    assert df["median_hh_income"].isna().all()


def test_parse_acs_builds_county_fips_from_state_and_county():
    payload = (b'[["NAME","B19013_001E","state","county"],'
               b'["Wake County, NC","88000","37","183"]]')
    df = covariates.parse_acs(payload, "county")
    assert df.iloc[0]["county_fips"] == "37183"


def test_parse_acs_builds_place_geoid():
    payload = (b'[["NAME","B19013_001E","state","place"],'
               b'["Raleigh city, NC","72000","37","55000"]]')
    df = covariates.parse_acs(payload, "place")
    assert df.iloc[0]["place_geoid"] == "3755000"


def test_derive_rates_uses_each_variables_own_universe():
    """Education is over adults 25+, not total population."""
    df = pd.DataFrame({
        "population": [1000], "race_total": [1000], "black_alone": [300],
        "edu_total": [600], "bachelors": [100], "masters": [40],
        "professional": [8], "doctorate": [2],
        "poverty_universe": [900], "poverty_count": [180],
    })
    out = covariates.derive_rates(df)
    assert out.iloc[0]["pct_black"] == 0.30
    # 150 of 600 adults 25+, NOT 150/1000
    assert out.iloc[0]["pct_bachelors_plus"] == 0.25
    # 180 of the 900-person poverty universe, NOT 180/1000
    assert out.iloc[0]["pct_below_poverty"] == 0.20


def test_derive_rates_sums_multi_part_numerators():
    df = pd.DataFrame({"vehicle_universe": [200], "owner_no_vehicle": [10],
                       "renter_no_vehicle": [30]})
    out = covariates.derive_rates(df)
    assert out.iloc[0]["pct_no_vehicle"] == 0.20


def test_derive_rates_handles_zero_denominator():
    df = pd.DataFrame({"race_total": [0], "black_alone": [0]})
    out = covariates.derive_rates(df)
    assert pd.isna(out.iloc[0]["pct_black"])


def test_derive_rates_skips_absent_denominators():
    out = covariates.derive_rates(pd.DataFrame({"population": [100]}))
    assert "pct_black" not in out.columns


def test_parse_crime_reads_live_cde_shape():
    """Verified against the live API: monthly buckets under offenses.actuals."""
    payload = (b'{"offenses":{"actuals":{'
               b'"Raleigh Police Department Offenses":'
               b'{"01-2022":10,"02-2022":15,"01-2023":20},'
               b'"Raleigh Police Department Clearances":'
               b'{"01-2022":3,"02-2022":4,"01-2023":5}}}}')
    df = covariates.parse_crime(payload, "NC0920100", "violent-crime")
    by_year = df.set_index("year")
    assert by_year.loc[2022, "actual"] == 25      # months summed to years
    assert by_year.loc[2022, "cleared"] == 7
    assert by_year.loc[2022, "months_reported"] == 2
    assert by_year.loc[2023, "actual"] == 20


def test_parse_crime_treats_null_month_as_missing_not_zero():
    payload = (b'{"offenses":{"actuals":{"X Offenses":'
               b'{"01-2022":10,"02-2022":null}}}}')
    df = covariates.parse_crime(payload, "X", "violent-crime")
    assert df.iloc[0]["actual"] == 10
    # a null month must not inflate the reported-month count
    assert df.iloc[0]["months_reported"] == 1


def test_parse_crime_handles_agency_with_no_actuals():
    df = covariates.parse_crime(b'{"offenses":{"actuals":{}}}', "X", "violent-crime")
    assert len(df) == 0
    assert list(df.columns) == ["ori9", "year", "offense", "actual",
                                "cleared", "months_reported"]


def test_parse_crime_tolerates_missing_clearances_series():
    payload = b'{"offenses":{"actuals":{"X Offenses":{"01-2022":7}}}}'
    df = covariates.parse_crime(payload, "X", "violent-crime")
    assert df.iloc[0]["actual"] == 7
    assert df.iloc[0]["cleared"] == 0


def test_parse_acs_builds_tract_geoid_from_state_county_tract():
    payload = (b'[["NAME","B19013_001E","state","county","tract"],'
               b'["Census Tract 1","61000","37","183","000101"]]')
    df = covariates.parse_acs(payload, "tract")
    assert df.iloc[0]["tract_geoid"] == "37183000101"


def test_tract_is_marked_as_a_per_state_level():
    assert "tract" in covariates.PER_STATE_LEVELS
    assert "{fips}" in covariates.GEO_CLAUSE["tract"][1]
