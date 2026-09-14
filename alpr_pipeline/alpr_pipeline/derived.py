"""Fast path: DeFlock / FlockHopper's pre-built feeds.

These are derived products, rebuilt daily from the same Overpass queries the
`harvest` module runs. Using them costs one HTTP request instead of ~200
Overpass queries, so it is the polite default for routine refreshes.

Trade-off: the publisher keeps only a whitelist of display attributes, so the
full raw OSM tag set, changeset IDs, and editor usernames are NOT present. Use
`harvest` when you need those.
"""

from __future__ import annotations

import gzip
import json
import logging

import requests

from .normalize import classify_vendor, clean_str, is_flock, parse_directions

log = logging.getLogger(__name__)

USER_AGENT = "alpr-research-pipeline/1.0 (academic research)"

# Cloudflare R2 behind the flockhopper-data Worker, rebuilt daily at 09:00 UTC.
FEEDS = {
    "US": "https://data.dontgetflocked.com/cameras.geojson.gz",
    "CA": "https://data.dontgetflocked.com/cameras-ca.geojson.gz",
}

# Legacy DeFlock feed: 20-degree region tiles behind an index. Still live and
# still updated hourly; kept as an independent cross-check on the primary feed.
DEFLOCK_REGION_INDEX = "https://cdn.deflock.me/regions/index.json"
DEFLOCK_COUNTS = "https://cdn.deflock.me/alpr-counts.json"


def _get(url: str, timeout: float = 300.0) -> requests.Response:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    return resp


def _decode_maybe_gzip(resp: requests.Response) -> dict:
    """Parse a JSON body that may or may not have been transparently decompressed.

    The R2 objects are stored gzipped with a `.gz` key. Whether requests has
    already inflated them depends on whether the edge set Content-Encoding, so
    sniff the magic bytes instead of trusting either.
    """
    content = resp.content
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    return json.loads(content.decode("utf-8"))


def fetch_feed(country: str = "US") -> tuple[list[dict], dict]:
    """Fetch one country's derived GeoJSON feed. Returns (records, metadata)."""
    url = FEEDS[country]
    log.info("Fetching derived feed: %s", url)
    resp = _get(url)
    data = _decode_maybe_gzip(resp)

    features = data.get("features") or []
    records = [_feature_to_record(f, country) for f in features]
    records = [r for r in records if r is not None]

    meta = {
        "source": "derived_feed",
        "url": url,
        "country": country,
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "feature_count": len(features),
        "record_count": len(records),
        "generated": data.get("metadata", {}).get("generated"),
    }
    log.info("Derived feed %s: %d records", country, len(records))
    return records, meta


def _feature_to_record(feature: dict, country: str) -> dict | None:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    props = feature.get("properties") or {}

    brand = clean_str(props.get("brand"))
    operator = clean_str(props.get("operator"))

    # The publisher pre-parses `direction` to degrees; re-derive the list form
    # from `directions` when present so multi-lens gantries stay complete.
    directions = props.get("directions") or (
        [props["direction"]] if props.get("direction") is not None else []
    )
    if not directions and props.get("directionCardinal"):
        directions = parse_directions(str(props["directionCardinal"]))

    # The feed is all-numeric today, but one bad value should drop that value,
    # not crash the whole fetch.
    numeric_directions: list[float] = []
    for d in directions:
        try:
            numeric_directions.append(float(d))
        except (TypeError, ValueError):
            log.debug("Dropping non-numeric direction %r on %s/%s",
                      d, props.get("osmType"), props.get("osmId"))

    return {
        "osm_type": props.get("osmType"),
        "osm_id": props.get("osmId"),
        "lat": round(lat, 7),
        "lon": round(lon, 7),
        "brand_raw": brand,
        "manufacturer_raw": None,
        "operator_raw": operator,
        "vendor": classify_vendor(brand, None, operator),
        "is_flock": is_flock(brand, None, operator),
        "direction_raw": clean_str(
            str(props["directionCardinal"]) if props.get("directionCardinal") else None
        ),
        "direction_deg": numeric_directions[0] if numeric_directions else None,
        "direction_count": len(numeric_directions),
        "directions_all": ";".join(f"{d:g}" for d in numeric_directions) or None,
        "surveillance_zone": clean_str(props.get("surveillanceZone")),
        "surveillance_kind": None,
        "mount_type": clean_str(props.get("mountType")),
        "camera_type": None,
        "support": None,
        "height": None,
        "ref": clean_str(props.get("ref")),
        "start_date": clean_str(props.get("startDate")),
        "operator_type": None,
        "description": None,
        "note": None,
        "website": None,
        "wikimedia_commons": None,
        "osm_version": props.get("osmVersion"),
        "osm_timestamp": props.get("osmTimestamp"),
        # Not published by the derived feed - only a full Overpass harvest has these.
        "osm_changeset": None,
        "osm_user": None,
        "osm_uid": None,
        "tag_count": None,
        "tags_json": None,
        "country_code": country,
    }


def fetch_deflock_counts() -> dict:
    """DeFlock's headline counters (hourly). Useful as an independent sanity check."""
    return _get(DEFLOCK_COUNTS, timeout=60).json()


def fetch_deflock_regions() -> tuple[list[dict], dict]:
    """Fetch the legacy DeFlock region-tile feed (cdn.deflock.me), worldwide.

    Independent of the FlockHopper R2 feed: different producer (an AWS Lambda),
    different cadence, same Overpass origin. Good for cross-validation.
    """
    index = _get(DEFLOCK_REGION_INDEX, timeout=60).json()
    tile_url = index["tile_url"]
    records: list[dict] = []

    for region in index["regions"]:
        lat, lon = region.split("/")
        url = tile_url.replace("{lat}", lat).replace("{lon}", lon)
        try:
            nodes = _get(url, timeout=120).json()
        except requests.HTTPError as exc:
            log.warning("region %s failed: %s", region, exc)
            continue

        for node in nodes:
            tags = node.get("tags") or {}
            brand = clean_str(tags.get("brand") or tags.get("surveillance:brand"))
            operator = clean_str(
                tags.get("operator") or tags.get("surveillance:operator")
            )
            manufacturer = clean_str(
                tags.get("manufacturer") or tags.get("surveillance:manufacturer")
            )
            directions = parse_directions(
                tags.get("direction") or tags.get("camera:direction")
            )
            records.append({
                "osm_type": "node",
                "osm_id": node["id"],
                "lat": round(float(node["lat"]), 7),
                "lon": round(float(node["lon"]), 7),
                "brand_raw": brand,
                "manufacturer_raw": manufacturer,
                "operator_raw": operator,
                "vendor": classify_vendor(brand, manufacturer, operator),
                "is_flock": is_flock(brand, manufacturer, operator),
                "direction_raw": clean_str(
                    tags.get("direction") or tags.get("camera:direction")
                ),
                "direction_deg": directions[0] if directions else None,
                "direction_count": len(directions),
                "directions_all": ";".join(f"{d:g}" for d in directions) or None,
                "tags_json": tags,
            })

    meta = {
        "source": "deflock_regions",
        "url": DEFLOCK_REGION_INDEX,
        "regions": len(index["regions"]),
        "record_count": len(records),
        "tile_size_degrees": index.get("tile_size_degrees"),
    }
    log.info("DeFlock regions: %d records across %d tiles",
             len(records), len(index["regions"]))
    return records, meta
