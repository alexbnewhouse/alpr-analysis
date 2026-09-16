import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon

from flock_alpr import geocode


def _square(x0, y0, size=1.0):
    return Polygon([(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)])


def _shapes():
    box = _square(-79, 35)
    return {
        "zcta": gpd.GeoDataFrame({"zcta": ["27601"], "geometry": [box]}, crs="EPSG:4326"),
        "place": gpd.GeoDataFrame({"place_geoid": ["3755000"], "geometry": [box]},
                                  crs="EPSG:4326"),
        "county": gpd.GeoDataFrame({"county_fips": ["37183"], "geometry": [box]},
                                   crs="EPSG:4326"),
    }


def test_join_assigns_all_three_levels():
    cams = pd.DataFrame({"osm_id": [1], "lat": [35.5], "lon": [-78.5]})
    out = geocode.join_geographies(cams, _shapes())
    assert out.iloc[0]["zcta"] == "27601"
    assert out.iloc[0]["place_geoid"] == "3755000"
    assert out.iloc[0]["county_fips"] == "37183"


def test_point_outside_all_polygons_gets_nulls_not_dropped():
    cams = pd.DataFrame({"osm_id": [1, 2], "lat": [35.5, 10.0], "lon": [-78.5, -10.0]})
    out = geocode.join_geographies(cams, _shapes())
    assert len(out) == 2
    assert pd.isna(out.set_index("osm_id").loc[2, "zcta"])


def test_rows_missing_coordinates_are_dropped():
    cams = pd.DataFrame({"osm_id": [1, 2], "lat": [35.5, None], "lon": [-78.5, None]})
    out = geocode.join_geographies(cams, _shapes())
    assert len(out) == 1
    assert out.iloc[0]["osm_id"] == 1


def test_original_columns_are_preserved():
    cams = pd.DataFrame({"osm_id": [1], "lat": [35.5], "lon": [-78.5],
                         "manufacturer": ["Flock Safety"]})
    out = geocode.join_geographies(cams, _shapes())
    assert out.iloc[0]["manufacturer"] == "Flock Safety"


def test_normalize_county_strips_jurisdiction_suffixes():
    assert geocode.normalize_county("Polk County") == "POLK"
    assert geocode.normalize_county("Caddo Parish") == "CADDO"
    assert geocode.normalize_county("Juneau City and Borough") == "JUNEAU"
    assert geocode.normalize_county("Nome Census Area") == "NOME"
    assert geocode.normalize_county("Wake") == "WAKE"
    # Virginia independent cities must stay distinct from same-named counties
    assert geocode.normalize_county("Richmond city") == "RICHMOND CITY"
    assert geocode.normalize_county("Richmond County") == "RICHMOND"
    assert geocode.normalize_county("") == ""
    assert geocode.normalize_county(None) == ""
