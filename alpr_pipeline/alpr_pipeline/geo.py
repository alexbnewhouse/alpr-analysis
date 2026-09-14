"""Reverse-geocoding to country / subdivision via cached public-domain boundaries.

Runs entirely offline after a one-time boundary download, so enriching 135k
points costs no API calls and is reproducible. Source: Natural Earth 10m
admin-0 (countries) and admin-1 (states/provinces), both public domain.

Two details matter for this dataset specifically:

* **US territories.** Natural Earth models Puerto Rico, the USVI, and Guam as
  their own admin-0 entities. ALPR research treats them as US, so they are
  folded back into country ``US`` with the territory code as the subdivision.

* **Bridges and coastlines.** A meaningful share of ALPRs sit on toll bridges
  and barrier islands, which fall *outside* even a 10m land polygon. A strict
  point-in-polygon test drops them. So an exact miss falls back to the nearest
  polygon within ``NEAREST_TOLERANCE_DEG``, which recovers them without
  assigning far-offshore noise to a random state.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import requests
from shapely.geometry import Point, shape
from shapely.prepared import prep
from shapely.strtree import STRtree

log = logging.getLogger(__name__)

NE_BASE = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"
)
COUNTRIES_URL = f"{NE_BASE}/ne_10m_admin_0_countries.geojson"
ADMIN1_URL = f"{NE_BASE}/ne_10m_admin_1_states_provinces.geojson"

# ~0.15 deg is roughly 16 km at the equator, less at US latitudes. Wide enough
# for any bridge span or barrier island, tight enough that a genuinely offshore
# point stays unassigned rather than being snapped to an arbitrary state.
NEAREST_TOLERANCE_DEG = 0.15

# NE admin-0 entities that US-focused analysis should count as US.
US_TERRITORIES = {"PR": "PR", "VI": "VI", "GU": "GU", "AS": "AS", "MP": "MP"}

# Clean ISO 3166-2 codes only. NE uses placeholder forms like "VI-X01~" for
# subdivisions it has not coded; the tilde is the tell.
_ISO_3166_2_RE = re.compile(r"^([A-Z]{2})-([A-Z0-9]{1,3})$")


def _download_cached(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("Downloading boundaries: %s", url)
    resp = requests.get(
        url, timeout=600, headers={"User-Agent": "alpr-research-pipeline/1.0"}
    )
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    log.info("Cached %s (%.1f MB)", dest.name, dest.stat().st_size / 1e6)
    return dest


class PolygonIndex:
    """R-tree index over named polygons, with exact then nearest lookup."""

    def __init__(self, entries: list[tuple[str, dict]]):
        """`entries` is a list of (name, geojson_geometry) pairs."""
        self.names: list[str] = []
        geoms = []
        for name, geom in entries:
            g = shape(geom)
            if g.is_empty:
                continue
            geoms.append(g)
            self.names.append(name)
        self.geoms = geoms
        self.tree = STRtree(geoms)
        # Prepared geometries are built on first use: preparing all 4,500+
        # 10m polygons up front costs more than the handful we actually test.
        self._prepared: dict[int, object] = {}

    def _covers(self, idx: int, pt: Point) -> bool:
        p = self._prepared.get(idx)
        if p is None:
            p = prep(self.geoms[idx])
            self._prepared[idx] = p
        return p.covers(pt)

    def lookup(self, lon: float, lat: float,
               tolerance: float = NEAREST_TOLERANCE_DEG) -> str | None:
        pt = Point(lon, lat)

        # Exact containment first: bbox candidates from the tree, confirmed.
        for idx in self.tree.query(pt):
            if self._covers(int(idx), pt):
                return self.names[int(idx)]

        if tolerance <= 0:
            return None

        # Fallback: nearest polygon, but only if it is genuinely close.
        nearest = self.tree.nearest(pt)
        if nearest is None:
            return None
        idx = int(nearest)
        if self.geoms[idx].distance(pt) <= tolerance:
            return self.names[idx]
        return None


class GeoEnricher:
    """Assigns ISO country code and subdivision (US state) to coordinates."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self._countries: PolygonIndex | None = None
        self._admin1: PolygonIndex | None = None

    @property
    def countries(self) -> PolygonIndex:
        if self._countries is None:
            path = _download_cached(COUNTRIES_URL, self.cache_dir / "ne_countries.geojson")
            data = json.loads(path.read_text())
            entries = []
            for f in data["features"]:
                p = f.get("properties") or {}
                geom = f.get("geometry")
                code = p.get("ISO_A2_EH") or p.get("ISO_A2")
                # NE marks unrecognised/disputed entries as "-99".
                if not geom or not code or code == "-99":
                    continue
                entries.append((str(code), geom))
            self._countries = PolygonIndex(entries)
            log.info("Loaded %d country polygons", len(entries))
        return self._countries

    @property
    def admin1(self) -> PolygonIndex:
        if self._admin1 is None:
            path = _download_cached(ADMIN1_URL, self.cache_dir / "ne_admin1.geojson")
            data = json.loads(path.read_text())
            entries = []
            for f in data["features"]:
                p = f.get("properties") or {}
                geom = f.get("geometry")
                if not geom:
                    continue
                code = None
                m = _ISO_3166_2_RE.match(str(p.get("iso_3166_2") or ""))
                if m:
                    code = m.group(2)
                elif p.get("postal"):
                    code = str(p["postal"])
                elif p.get("name"):
                    code = str(p["name"])
                if code:
                    entries.append((code, geom))
            self._admin1 = PolygonIndex(entries)
            log.info("Loaded %d admin-1 polygons", len(entries))
        return self._admin1

    def enrich(self, lon: float, lat: float) -> tuple[str | None, str | None]:
        """Return (country_code, subdivision_code).

        US territories are normalized to country ``US``; their territory code
        becomes the subdivision, so PR/VI/GU rows group with the states.
        """
        country = self.countries.lookup(lon, lat)
        if country is None:
            return None, None

        if country in US_TERRITORIES:
            return "US", US_TERRITORIES[country]

        return country, self.admin1.lookup(lon, lat)
