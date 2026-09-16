import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Polygon

from flock_alpr import roads

CRS = roads.EQUAL_AREA_CRS


def _two_tracts_sharing_an_edge():
    """Two 1km squares meeting along x = 1000."""
    left = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])
    right = Polygon([(1000, 0), (2000, 0), (2000, 1000), (1000, 1000)])
    return gpd.GeoDataFrame(
        {"tract_geoid": ["A", "B"], "geometry": [left, right]}, crs=CRS
    )


def _road(line):
    return gpd.GeoDataFrame(
        {"LINEARID": ["R1"], "MTFCC": ["S1200"], "geometry": [line]}, crs=CRS
    )


def test_road_on_a_shared_boundary_is_not_double_counted():
    """Census boundaries are often drawn down the middle of major roads.

    Such a road lies on the shared edge of both closed polygons, so a naive
    intersection credits its full length to each -- doubling the total.
    """
    on_edge = _road(LineString([(1000, 0), (1000, 1000)]))   # exactly the shared edge
    out = roads.road_km_by_unit(on_edge, _two_tracts_sharing_an_edge(), "tract_geoid")
    total = out["road_km_secondary"].sum()
    assert total == pytest_approx(1.0), f"1km boundary road totalled {total} km"
    # and it is split evenly between the two neighbours
    assert sorted(out["road_km_secondary"].round(4)) == [0.5, 0.5]


def test_interior_road_keeps_its_full_length():
    """A road well inside one polygon must not be halved by the correction."""
    inside = _road(LineString([(200, 500), (800, 500)]))     # 600 m, interior to A
    out = roads.road_km_by_unit(inside, _two_tracts_sharing_an_edge(), "tract_geoid")
    assert out.loc[out["tract_geoid"] == "A", "road_km_secondary"].iloc[0] == \
        pytest_approx(0.6)


def test_road_crossing_a_boundary_is_split_not_duplicated():
    """A road passing through both units is halved between them, not doubled.

    It loses at most one tolerance-band width (2 x BOUNDARY_TOL_M) where it
    crosses the boundary, because that sliver is treated as boundary-lying and
    halved. Here that is 1 m on a 1 km road; on real arterials the effect is
    invisible (North Carolina reconciles to 0.9998 of raw length).
    """
    crossing = _road(LineString([(500, 500), (1500, 500)]))  # 1km across both
    out = roads.road_km_by_unit(crossing, _two_tracts_sharing_an_edge(), "tract_geoid")
    total = out["road_km_secondary"].sum()
    max_loss_km = 2 * roads.BOUNDARY_TOL_M / 1000.0
    assert 1.0 - max_loss_km <= total <= 1.0, f"crossing road totalled {total} km"
    assert sorted(out["road_km_secondary"].round(3)) == [0.5, 0.5]


def test_primary_and_secondary_are_kept_separate():
    both = gpd.GeoDataFrame(
        {"LINEARID": ["R1", "R2"],
         "MTFCC": ["S1100", "S1200"],
         "geometry": [LineString([(200, 300), (800, 300)]),
                      LineString([(200, 700), (800, 700)])]},
        crs=CRS,
    )
    out = roads.road_km_by_unit(both, _two_tracts_sharing_an_edge(), "tract_geoid")
    row = out[out["tract_geoid"] == "A"].iloc[0]
    assert row["road_km_primary"] == pytest_approx(0.6)
    assert row["road_km_secondary"] == pytest_approx(0.6)


def test_unit_with_one_class_reports_zero_for_the_other_not_null():
    only_secondary = _road(LineString([(200, 500), (800, 500)]))
    out = roads.road_km_by_unit(only_secondary, _two_tracts_sharing_an_edge(),
                                "tract_geoid")
    assert out["road_km_primary"].notna().all()
    assert out.loc[out["tract_geoid"] == "A", "road_km_primary"].iloc[0] == 0.0


def pytest_approx(x, tol=1e-3):
    class _A:
        def __eq__(self, other):
            return abs(other - x) < tol
        def __repr__(self):
            return f"~{x}"
    return _A()
