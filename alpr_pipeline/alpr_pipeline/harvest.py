"""Adaptive-tile harvest of every ALPR element in OpenStreetMap.

A single worldwide `out meta` query returns ~135k elements / ~60MB and reliably
trips Overpass gateway timeouts. So we cover the globe with a coarse grid, probe
each cell with a cheap `out count`, recursively quarter any cell holding more
than SPLIT_THRESHOLD cameras, and only then fetch the leaves. Every request
stays small, and the grid self-adapts as the network grows.

This is the same strategy FlockHopper's Cloudflare Worker uses, generalized from
US-only to worldwide, and retaining the *full* raw OSM tag set plus edit
metadata rather than a whitelist of display attributes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .normalize import (
    classify_vendor,
    clean_str,
    is_flock,
    is_flock_qid,
    parse_directions,
)
from .wikidata import valid_qid
from .overpass import OverpassClient

log = logging.getLogger(__name__)

# The OSM tag pair that defines an ALPR. This is the crowdsourced convention
# DeFlock standardized on and documents at deflock.org.
ALPR_SELECTOR = '["man_made"="surveillance"]["surveillance:type"="ALPR"]'

SPLIT_THRESHOLD = 4_000  # quarter any tile holding more cameras than this
MIN_TILE_SPAN = 0.05     # deg - safety floor, stop subdividing below this
FETCH_TOLERANCE = 0.15   # allowed drift between a tile's probe and its fetch
TILE_RETRIES = 3         # retries for a tile whose fetch fails its integrity check
TILE_RETRY_DELAY = 2.0   # seconds between those retries

# Floor on an unscoped (worldwide) harvest. A count probe that returns HTTP 200
# with an empty body reads as "0 cameras here", and a zero-count tile is dropped
# before it ever reaches the per-tile integrity check -- so a single hiccup can
# silently delete a whole 30-degree region with no error raised. This total-count
# floor is the backstop for that, mirroring RAW_MIN_TOTAL in the reference
# implementation. Skipped for --bbox runs, which are legitimately small.
MIN_WORLDWIDE_TOTAL = 50_000


@dataclass
class Tile:
    s: float
    w: float
    n: float
    e: float
    probed: int = 0

    @property
    def bbox(self) -> str:
        return f"{self.s},{self.w},{self.n},{self.e}"

    @property
    def span(self) -> float:
        return min(self.n - self.s, self.e - self.w)

    def quarters(self) -> list["Tile"]:
        my = (self.s + self.n) / 2
        mx = (self.w + self.e) / 2
        return [
            Tile(self.s, self.w, my, mx),
            Tile(self.s, mx, my, self.e),
            Tile(my, self.w, self.n, mx),
            Tile(my, mx, self.n, self.e),
        ]


@dataclass
class HarvestStats:
    tiles_probed: int = 0
    tiles_fetched: int = 0
    raw_elements: int = 0
    endpoints_used: set[str] = field(default_factory=set)
    osm_base_timestamp: str | None = None


def build_seed_tiles(bbox: tuple[float, float, float, float] | None = None,
                     step: float = 10.0,
                     region: str = "world") -> list[Tile]:
    """Seed grid for the harvest.

    Cell size is a real constraint, not a tuning knob: an `out count` probe over
    a 30-degree cell containing the US east coast is expensive enough that every
    Overpass mirror returns 504 or times out, which kills the whole run. Keep
    seed cells small enough that a probe answers in seconds.

    `region="us"` uses the same seeding as the reference implementation
    (~6.5 x 9.84 degree cells over the lower 48, plus AK/HI/PR), which is known
    to work against live Overpass.
    """
    if bbox is not None:
        return [Tile(*bbox)]

    if region == "us":
        tiles: list[Tile] = []
        s = 24.0
        while s < 50.0:
            w = -125.0
            while w < -66.0:
                tiles.append(Tile(s, w, min(s + 6.5, 50.0), min(w + 9.84, -66.0)))
                w += 9.84
            s += 6.5
        tiles.append(Tile(51, -180, 72, -129))      # Alaska
        tiles.append(Tile(18, -161, 23, -154))      # Hawaii
        tiles.append(Tile(17.5, -67.5, 18.7, -64.5))  # Puerto Rico + USVI
        return tiles

    tiles = []
    lat = -90.0
    while lat < 90.0:
        lon = -180.0
        while lon < 180.0:
            tiles.append(
                Tile(lat, lon, min(lat + step, 90.0), min(lon + step, 180.0))
            )
            lon += step
        lat += step
    return tiles


def _selector_for(tile: Tile) -> str:
    b = tile.bbox
    return (
        f"node{ALPR_SELECTOR}({b});"
        f"way{ALPR_SELECTOR}({b});"
    )


def plan_leaf_tiles(client: OverpassClient, seed: list[Tile],
                    stats: HarvestStats) -> list[Tile]:
    """Expand the seed grid into leaves each holding <= SPLIT_THRESHOLD cameras."""
    leaves: list[Tile] = []
    queue = list(seed)

    while queue:
        tile = queue.pop(0)
        count = client.count(_selector_for(tile))
        stats.tiles_probed += 1

        if count == 0:
            continue
        if count <= SPLIT_THRESHOLD or tile.span <= MIN_TILE_SPAN:
            tile.probed = count
            leaves.append(tile)
            log.info("leaf %s -> %d cameras", tile.bbox, count)
            continue

        log.info("splitting %s (%d cameras)", tile.bbox, count)
        queue.extend(tile.quarters())

    return leaves


def extract_elements(elements: list[dict], out: dict[str, dict]) -> None:
    """Convert an Overpass element batch into camera records, merged into `out`.

    Keyed `type/id` so a camera appearing in two overlapping tiles is stored
    once. Ways get a centroid computed from their child nodes, which Overpass
    returns alongside them via the `>;` recursion.
    """
    nodes_by_id = {
        el["id"]: (el["lat"], el["lon"])
        for el in elements
        if el.get("type") == "node"
        and el.get("lat") is not None
        and el.get("lon") is not None
    }

    for el in elements:
        tags = el.get("tags") or {}
        # The recursion pulls in child nodes that are not themselves cameras.
        if tags.get("man_made") != "surveillance":
            continue
        if tags.get("surveillance:type") != "ALPR":
            continue

        lat, lon = el.get("lat"), el.get("lon")
        if el.get("type") == "way" and el.get("nodes"):
            coords = [nodes_by_id[n] for n in el["nodes"] if n in nodes_by_id]
            if coords:
                lat = sum(c[0] for c in coords) / len(coords)
                lon = sum(c[1] for c in coords) / len(coords)
        if lat is None or lon is None:
            continue

        out[f"{el['type']}/{el['id']}"] = build_record(el, tags, lat, lon)


def build_record(el: dict, tags: dict, lat: float, lon: float) -> dict:
    """Flatten one OSM element into the pipeline's camera record shape."""
    brand = clean_str(tags.get("brand") or tags.get("surveillance:brand"))
    manufacturer = clean_str(
        tags.get("manufacturer") or tags.get("surveillance:manufacturer")
    )
    operator = clean_str(tags.get("operator") or tags.get("surveillance:operator"))

    direction_raw = tags.get("direction") or tags.get("camera:direction")
    directions = parse_directions(direction_raw)

    brand_qid = valid_qid(tags.get("brand:wikidata"))
    manufacturer_qid = valid_qid(tags.get("manufacturer:wikidata"))
    operator_qid = valid_qid(tags.get("operator:wikidata"))

    return {
        "osm_type": el["type"],
        "osm_id": el["id"],
        "lat": round(float(lat), 7),
        "lon": round(float(lon), 7),
        # --- vendor / ownership
        "brand_raw": brand,
        "manufacturer_raw": manufacturer,
        "operator_raw": operator,
        "brand_wikidata": brand_qid,
        "manufacturer_wikidata": manufacturer_qid,
        "operator_wikidata": operator_qid,
        "vendor": classify_vendor(brand, manufacturer, operator),
        # A Wikidata Q-ID settles the question regardless of how the free-text
        # brand happens to be spelled, so it can only ever add confidence.
        "is_flock": (
            is_flock(brand, manufacturer, operator)
            or is_flock_qid(brand_qid, manufacturer_qid)
        ),
        # --- orientation
        "direction_raw": clean_str(direction_raw),
        "direction_deg": directions[0] if directions else None,
        "direction_count": len(directions),
        "directions_all": ";".join(f"{d:g}" for d in directions) or None,
        # --- physical / deployment context
        "surveillance_zone": clean_str(tags.get("surveillance:zone")),
        "surveillance_kind": clean_str(tags.get("surveillance")),
        "mount_type": clean_str(tags.get("camera:mount")),
        "camera_type": clean_str(tags.get("camera:type")),
        "support": clean_str(tags.get("support")),
        "height": clean_str(tags.get("height")),
        "ref": clean_str(tags.get("ref")),
        "start_date": clean_str(tags.get("start_date")),
        "operator_type": clean_str(tags.get("operator:type")),
        "description": clean_str(tags.get("description")),
        "note": clean_str(tags.get("note")),
        "website": clean_str(tags.get("website")),
        "wikimedia_commons": clean_str(tags.get("wikimedia_commons")),
        # --- OSM provenance / edit metadata
        "osm_version": el.get("version"),
        "osm_timestamp": el.get("timestamp"),
        "osm_changeset": el.get("changeset"),
        "osm_user": el.get("user"),
        "osm_uid": el.get("uid"),
        "tag_count": len(tags),
        "tags_json": tags,
    }


def _fetch_tile(client: OverpassClient, tile: Tile,
                stats: HarvestStats) -> dict[str, dict]:
    """Fetch one leaf tile, retrying if the response fails its integrity check.

    A short response is usually a transient truncation, so it is retried rather
    than treated as fatal on the first occurrence -- one flaky reply should not
    abort a ~200-request worldwide harvest. If it persists we fail closed, since
    the alternative is writing a silent hole into the dataset.
    """
    ql = f"[out:json][timeout:180];({_selector_for(tile)});out meta;>;out skel qt;"
    last_error: str = ""

    for attempt in range(TILE_RETRIES):
        result = client.query(ql, allow_empty=True)
        stats.endpoints_used.add(result.endpoint)

        osm3s = result.data.get("osm3s") or {}
        if osm3s.get("timestamp_osm_base"):
            stats.osm_base_timestamp = osm3s["timestamp_osm_base"]

        local: dict[str, dict] = {}
        extract_elements(result.data.get("elements") or [], local)

        if not tile.probed or len(local) >= tile.probed * (1 - FETCH_TOLERANCE):
            return local

        last_error = (
            f"got {len(local)} records, probe expected {tile.probed}"
        )
        log.warning("Tile %s integrity check failed (%s); attempt %d/%d",
                    tile.bbox, last_error, attempt + 1, TILE_RETRIES)
        if attempt < TILE_RETRIES - 1:
            time.sleep(TILE_RETRY_DELAY * (attempt + 1))

    raise RuntimeError(
        f"Tile {tile.bbox} integrity check failed after {TILE_RETRIES} "
        f"attempts: {last_error}"
    )


def harvest(client: OverpassClient,
            bbox: tuple[float, float, float, float] | None = None,
            seed_step: float = 10.0,
            region: str = "world") -> tuple[list[dict], HarvestStats]:
    """Run a full adaptive-tile harvest. Returns (records, stats)."""
    stats = HarvestStats()

    seed = build_seed_tiles(bbox, seed_step, region)
    log.info("Probing %d seed tiles...", len(seed))
    leaves = plan_leaf_tiles(client, seed, stats)
    expected = sum(t.probed for t in leaves)
    log.info("Planned %d leaf tiles, ~%d cameras expected", len(leaves), expected)

    merged: dict[str, dict] = {}
    for i, tile in enumerate(leaves, 1):
        local = _fetch_tile(client, tile, stats)
        merged.update(local)
        stats.tiles_fetched += 1
        log.info("[%d/%d] %s -> %d records (total %d)",
                 i, len(leaves), tile.bbox, len(local), len(merged))

    # Applies to both national seedings; a --bbox run is legitimately small.
    if bbox is None and len(merged) < MIN_WORLDWIDE_TOTAL:
        raise RuntimeError(
            f"Harvest returned only {len(merged)} cameras (floor "
            f"{MIN_WORLDWIDE_TOTAL}). A count probe most likely failed open and "
            f"dropped a region. Refusing to write a partial dataset."
        )

    stats.raw_elements = len(merged)
    records = sorted(merged.values(), key=lambda r: (r["osm_type"], r["osm_id"]))
    return records, stats
