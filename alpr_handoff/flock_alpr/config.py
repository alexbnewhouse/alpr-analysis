"""Paths, endpoints, and constants shared across pipeline stages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
CACHE = RAW / "cache"
TIGER_DIR = RAW / "tiger"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Tried in order when the primary is overloaded. Large states (CA, TX) push the
# main endpoint into 504s under load; the mirrors have different queues.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
]
OHSOME_URL = "https://api.ohsome.org/v1"
AOS_CSV_URL = "https://atlasofsurveillance.org/download.csv"
CENSUS_ACS_URL = "https://api.census.gov/data/{year}/acs/acs5"
FBI_CDE_URL = "https://api.usa.gov/crime/fbi/cde"

CENSUS_KEY_SIGNUP = "https://api.census.gov/data/key_signup.html"
FBI_KEY_SIGNUP = "https://api.data.gov/signup/"

STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]

# FIPS state codes, needed for per-state TIGER place shapefiles.
STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}

for _p in (DATA, RAW, INTERIM, CACHE, TIGER_DIR):
    _p.mkdir(parents=True, exist_ok=True)
