import pandas as pd

from flock_alpr import build_panel


def _cams():
    return pd.DataFrame({
        "osm_id": [1, 2, 3],
        "zcta": ["27601", "27601", "28202"],
        "county_fips": ["37183", "37183", "37119"],
        "manufacturer": ["Flock Safety", "Axis Communications", "Flock Safety"],
        "osm_timestamp": pd.to_datetime(
            ["2025-01-01", "2025-06-01", "2025-03-01"], utc=True
        ),
    })


def test_aggregate_counts_total_and_flock_separately():
    out = build_panel.aggregate_cameras(_cams(), "zcta").set_index("zcta")
    assert out.loc["27601", "camera_count"] == 2
    assert out.loc["27601", "flock_count"] == 1
    assert out.loc["28202", "flock_count"] == 1


def test_aggregate_tracks_first_and_last_seen():
    out = build_panel.aggregate_cameras(_cams(), "zcta").set_index("zcta")
    assert str(out.loc["27601", "first_seen"]).startswith("2025-01-01")
    assert str(out.loc["27601", "last_seen"]).startswith("2025-06-01")


def test_aggregate_drops_rows_with_null_geography():
    cams = _cams()
    cams.loc[0, "zcta"] = None
    out = build_panel.aggregate_cameras(cams, "zcta")
    assert out["camera_count"].sum() == 2


def test_discovery_lag_computed_in_days():
    osm = pd.DataFrame({
        "ori9": ["FL0530000"],
        "osm_first_seen": pd.to_datetime(["2025-06-01"], utc=True),
    })
    aos = pd.DataFrame({
        "ori9": ["FL0530000"],
        "earliest_source_date": pd.to_datetime(["2025-05-01"], utc=True),
    })
    out = build_panel.discovery_lag(osm, aos)
    assert out.iloc[0]["lag_days"] == 31


def test_discovery_lag_can_be_negative():
    osm = pd.DataFrame({
        "ori9": ["FL0530000"],
        "osm_first_seen": pd.to_datetime(["2025-01-01"], utc=True),
    })
    aos = pd.DataFrame({
        "ori9": ["FL0530000"],
        "earliest_source_date": pd.to_datetime(["2025-03-02"], utc=True),
    })
    out = build_panel.discovery_lag(osm, aos)
    assert out.iloc[0]["lag_days"] == -60


def test_geo_panel_has_no_duplicate_keys():
    acs = pd.DataFrame({"zcta": ["27601"], "median_hh_income": [54321],
                        "population": [10000]})
    panel = build_panel.build_geo_panel(_cams(), acs, "zcta")
    assert not panel["zcta"].duplicated().any()


def test_geo_panel_computes_per_capita_rates():
    acs = pd.DataFrame({"zcta": ["27601"], "median_hh_income": [54321],
                        "population": [10000]})
    panel = build_panel.build_geo_panel(_cams(), acs, "zcta").set_index("zcta")
    assert panel.loc["27601", "cameras_per_10k"] == 2.0
    assert panel.loc["27601", "flock_per_10k"] == 1.0


def test_geo_panel_without_acs_returns_counts_only():
    panel = build_panel.build_geo_panel(_cams(), None, "zcta")
    assert "camera_count" in panel.columns
    assert len(panel) == 2


def test_osm_first_seen_by_county_takes_minimum():
    out = build_panel.osm_first_seen_by_county(_cams()).set_index("county_fips")
    assert str(out.loc["37183", "osm_first_seen"]).startswith("2025-01-01")


def test_agency_panel_excludes_null_ori():
    aos = pd.DataFrame({
        "ori9": ["FL0530000", None],
        "agency": ["Polk County SO", "Unknown PD"],
        "vendor": ["Flock Safety", "Flock Safety"],
    })
    panel = build_panel.build_agency_panel(aos)
    assert len(panel) == 1
    assert panel.iloc[0]["ori9"] == "FL0530000"


def test_attach_county_fips_bridges_atlas_names_to_tiger():
    aos = pd.DataFrame({
        "ori9": ["FL0530000", "LA0170000"],
        "state": ["FL", "LA"],
        "county": ["Polk County", "Caddo Parish"],
    })
    crosswalk = pd.DataFrame({
        "county_fips": ["12105", "22017"],
        "state": ["FL", "LA"],
        "county_norm": ["POLK", "CADDO"],
    })
    out = build_panel.attach_county_fips(aos, crosswalk)
    assert out.set_index("ori9").loc["FL0530000", "county_fips"] == "12105"
    assert out.set_index("ori9").loc["LA0170000", "county_fips"] == "22017"


def test_attach_county_fips_leaves_unmatched_as_null():
    aos = pd.DataFrame({"ori9": ["XX1234567"], "state": ["FL"],
                        "county": ["Nowhere County"]})
    crosswalk = pd.DataFrame({"county_fips": ["12105"], "state": ["FL"],
                              "county_norm": ["POLK"]})
    out = build_panel.attach_county_fips(aos, crosswalk)
    assert len(out) == 1
    assert pd.isna(out.iloc[0]["county_fips"])


def test_osm_first_seen_by_agency_takes_county_minimum():
    aos_fips = pd.DataFrame({"ori9": ["FL0530000"], "county_fips": ["12105"]})
    osm_county = pd.DataFrame({
        "county_fips": ["12105"],
        "osm_first_seen": pd.to_datetime(["2025-02-01"], utc=True),
    })
    out = build_panel.osm_first_seen_by_agency(aos_fips, osm_county)
    assert len(out) == 1
    assert str(out.iloc[0]["osm_first_seen"]).startswith("2025-02-01")


def test_osm_first_seen_by_agency_skips_rows_without_fips():
    aos_fips = pd.DataFrame({"ori9": ["A", "B"], "county_fips": ["12105", None]})
    osm_county = pd.DataFrame({
        "county_fips": ["12105"],
        "osm_first_seen": pd.to_datetime(["2025-02-01"], utc=True),
    })
    out = build_panel.osm_first_seen_by_agency(aos_fips, osm_county)
    assert out["ori9"].tolist() == ["A"]
