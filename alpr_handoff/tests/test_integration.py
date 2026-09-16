"""Live-API checks. Deselect with: pytest -m "not network"

These guard against silent upstream changes — a renamed Atlas column, a
retagged OSM scheme, an ohsome response reshape — that unit tests against
committed fixtures cannot see.
"""
import pytest

from flock_alpr import extract_aos, extract_osm, extract_osm_history, http, config

pytestmark = pytest.mark.network


def test_atlas_csv_still_parses_with_expected_scale():
    df = extract_aos.parse_aos(http.fetch(config.AOS_CSV_URL))
    assert len(df) > 3500, "Atlas ALPR row count collapsed; check the schema"
    assert df["is_flock"].sum() > 2000
    assert df["state"].nunique() > 40


def test_ori_parse_rate_stays_high():
    df = extract_aos.parse_aos(http.fetch(config.AOS_CSV_URL))
    flock = df[df["is_flock"]]
    rate = flock["ori9_valid"].mean()
    assert rate > 0.95, f"ORI parse rate fell to {rate:.1%}; upstream format changed"


def test_nc_overpass_returns_flock_as_modal_manufacturer():
    payload = http.fetch(
        config.OVERPASS_URL, method="POST",
        data=extract_osm.build_query("NC").encode(), timeout=300,
    )
    df = extract_osm.parse_overpass(payload, "NC")
    assert len(df) > 3000, "NC ALPR node count dropped; check the OSM tag scheme"
    assert df["manufacturer"].value_counts().index[0] == "Flock Safety"
    assert df["lat"].notna().all()


def test_ohsome_window_is_queryable():
    lo, hi = extract_osm_history.data_window()
    assert lo < hi
    assert lo.startswith("20")
