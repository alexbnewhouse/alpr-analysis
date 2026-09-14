"""Command-line entry point for the ALPR collection pipeline.

    python -m alpr_pipeline fetch   --source derived     # fast, 1 request
    python -m alpr_pipeline fetch   --source overpass    # full raw tags
    python -m alpr_pipeline export  --flock-only --format csv parquet xlsx
    python -m alpr_pipeline summary
    python -m alpr_pipeline verify
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .derived import (
    fetch_deflock_counts,
    fetch_deflock_regions,
    fetch_feed,
)
from .geo import GeoEnricher
from .harvest import harvest
from .overpass import DEFAULT_USER_AGENT, OverpassClient
from .store import CameraStore, export_all
from .wikidata import WikidataLabels

DEFAULT_DB = Path("data/alpr.sqlite")
DEFAULT_OUT = Path("data")
CACHE_DIR = Path("data/cache")

log = logging.getLogger("alpr_pipeline")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _enrich_geo(records: list[dict], cache_dir: Path) -> None:
    """Attach country_code and US state in place."""
    enricher = GeoEnricher(cache_dir)
    log.info("Reverse-geocoding %d records (offline boundaries)...", len(records))
    for i, rec in enumerate(records, 1):
        country, state = enricher.enrich(rec["lon"], rec["lat"])
        # Prefer the boundary-derived country over whichever feed the record came
        # from: it is per-point rather than per-feed, and it keeps country and
        # state mutually consistent (a feed labelled "US" can still carry a
        # handful of cross-border nodes near Mexico or Canada).
        rec["country_code"] = country or rec.get("country_code")
        rec["state"] = state
        if i % 20000 == 0:
            log.info("  geocoded %d/%d", i, len(records))


def _enrich_wikidata(records: list[dict], cache_dir: Path) -> None:
    """Resolve `*:wikidata` Q-IDs to vendor labels, in place.

    Manufacturer wins over brand: on ALPR nodes the manufacturer tag names who
    built the camera, which is the attribution question this column answers.
    """
    qids = {
        q
        for rec in records
        for q in (rec.get("manufacturer_wikidata"), rec.get("brand_wikidata"))
        if q
    }
    if not qids:
        return

    labels = WikidataLabels(cache_dir).resolve(qids)
    log.info("Resolved %d/%d Wikidata Q-IDs to labels", len(labels), len(qids))
    for rec in records:
        qid = rec.get("manufacturer_wikidata") or rec.get("brand_wikidata")
        rec["vendor_wikidata"] = labels.get(qid) if qid else None


def cmd_fetch(args: argparse.Namespace) -> int:
    store = CameraStore(args.db)

    if args.source == "overpass":
        client = OverpassClient(
            user_agent=args.user_agent, min_interval=args.min_interval
        )
        bbox = tuple(args.bbox) if args.bbox else None
        records, stats = harvest(client, bbox=bbox, seed_step=args.seed_step,
                                 region=args.region)
        endpoint = ", ".join(sorted(stats.endpoints_used))
        osm_base = stats.osm_base_timestamp
        notes = (
            f"tiles_probed={stats.tiles_probed} tiles_fetched={stats.tiles_fetched}"
            + (f" bbox={bbox}" if bbox else " worldwide")
        )
        source = "overpass"

    elif args.source == "derived":
        records, osm_base, notes = [], None, ""
        metas = []
        for country in args.countries:
            recs, meta = fetch_feed(country)
            records.extend(recs)
            metas.append(meta)
        endpoint = ", ".join(m["url"] for m in metas)
        notes = json.dumps(metas)
        source = "derived_feed"

    elif args.source == "deflock-regions":
        records, meta = fetch_deflock_regions()
        endpoint = meta["url"]
        osm_base = None
        notes = json.dumps(meta)
        source = "deflock_regions"

    else:  # pragma: no cover - argparse constrains this
        raise ValueError(args.source)

    if not records:
        log.error("No records fetched; refusing to write an empty snapshot.")
        store.close()
        return 1

    if not args.no_geo:
        _enrich_geo(records, args.cache_dir)
    if not args.no_wikidata:
        _enrich_wikidata(records, args.cache_dir)

    snapshot_id = store.begin_snapshot(source, endpoint, notes)
    # Only an Overpass harvest carries every column; the derived feeds publish a
    # display whitelist, so they must not overwrite richer stored data with NULL.
    result = store.write_records(
        snapshot_id, records, complete=(args.source == "overpass")
    )
    store.finish_snapshot(
        snapshot_id, result["records"], result["flock"], osm_base
    )

    log.info(
        "Snapshot %d: %d records (%d Flock) -> %s",
        snapshot_id, result["records"], result["flock"], args.db,
    )

    if args.export:
        export_all(store, args.out, flock_only=False, formats=tuple(args.format))
    store.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = CameraStore(args.db)
    paths = export_all(
        store, args.out, flock_only=args.flock_only,
        formats=tuple(args.format), country=args.country,
    )
    store.close()
    for p in paths:
        print(p)
    return 0


def cmd_covariates(args: argparse.Namespace) -> int:
    """Join census geography + ACS covariates onto the camera data."""
    from .covariates import SUMMARY_LEVELS
    from .covariates.pipeline import run as run_covariates

    store = CameraStore(args.db)
    cameras = store.dataframe(country="US")
    store.close()

    if cameras.empty:
        log.error("No US cameras in %s. Run `fetch` first.", args.db)
        return 1
    log.info("Loaded %d US cameras", len(cameras))

    crime_identity = None
    if args.crime:
        from .covariates.crime import build_identity
        missing = [f for f in ("name", "email", "institution",
                               "research_question")
                   if not getattr(args, f, None)]
        if missing:
            log.error(
                "--crime downloads a guestbook-gated file from Harvard "
                "Dataverse, which discloses who you are. Supply %s.",
                ", ".join("--" + m.replace("_", "-") for m in missing),
            )
            return 1
        crime_identity = build_identity(
            name=args.name, email=args.email, institution=args.institution,
            research_question=args.research_question,
        )

    cameras_joined, covariates, panel = run_covariates(
        cameras, args.level, args.cache_dir,
        extra_levels=args.also_assign, year=args.year, force=args.refresh,
        political=args.political, crime=args.crime,
        crime_identity=crime_identity, crime_year=args.crime_year,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    lvl = args.level
    written = []
    for name, df in (
        (f"cameras_with_covariates_{lvl}", cameras_joined),
        (f"acs{args.year}_{lvl}", covariates),
        (f"{lvl}_panel", panel),
    ):
        for fmt in args.format:
            path = out / f"{name}.{fmt}"
            if fmt == "csv":
                df.to_csv(path, index=False)
            elif fmt == "parquet":
                df.to_parquet(path, index=False)
            written.append(path)

    for p in written:
        log.info("wrote %s (%.1f MB)", p, p.stat().st_size / 1e6)
        print(p)

    print(f"\n{SUMMARY_LEVELS[lvl].name} level — {SUMMARY_LEVELS[lvl].notes}")
    print(f"Geographies: {len(panel):,}  |  with >=1 camera: "
          f"{int(panel['has_camera'].sum()):,} "
          f"({panel['has_camera'].mean():.1%})")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    store = CameraStore(args.db)
    s = store.summary()
    print(f"\nTotal cameras : {s['total']:,}")
    print(f"Flock Safety  : {s['flock']:,} ({s['flock'] / max(s['total'], 1):.1%})")

    print("\nBy vendor:")
    for row in s["by_vendor"][:15]:
        print(f"  {row['v']:<24} {row['n']:>8,}")

    print("\nBy country:")
    for row in s["by_country"]:
        print(f"  {row['cc']:<24} {row['n']:>8,}")

    print("\nTop US states:")
    for row in s["by_state"]:
        print(f"  {row['s']:<24} {row['n']:>8,}")

    print("\nSnapshots:")
    for row in store.conn.execute(
        "SELECT snapshot_id, started_utc, source, record_count, flock_count, "
        "osm_base_utc FROM snapshots ORDER BY snapshot_id"
    ):
        print(f"  #{row['snapshot_id']} {row['started_utc']} {row['source']:<16} "
              f"{row['record_count'] or 0:>8,} rec  {row['flock_count'] or 0:>8,} flock"
              f"  osm_base={row['osm_base_utc'] or '-'}")
    store.close()
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Cross-check the local DB against independent upstream counters.

    Compares per country rather than against the worldwide total: a snapshot
    taken from the US+CA derived feeds is legitimately ~10k short of the
    worldwide Overpass count, and a global drift figure would flag that
    difference in scope as if it were staleness.
    """
    store = CameraStore(args.db)
    # Compare only what the latest snapshot still sees: the cumulative table
    # retains cameras since deleted from OSM, which would read as false drift.
    local = store.summary(latest_only=True)
    local_by_country = {r["cc"]: r["n"] for r in local["by_country"]}
    store.close()

    client = OverpassClient(user_agent=args.user_agent)
    node_way = (
        'node["man_made"="surveillance"]["surveillance:type"="ALPR"]{scope};'
        'way["man_made"="surveillance"]["surveillance:type"="ALPR"]{scope};'
    )

    world = client.count(node_way.replace("{scope}", ""))
    print(f"\nLocal DB total       : {local['total']:,}")
    print(f"Overpass worldwide   : {world:,}")
    print(f"Coverage of world    : {local['total'] / max(world, 1):.1%}"
          f"  (scope: {', '.join(sorted(local_by_country))})")

    try:
        counts = fetch_deflock_counts()
        print(f"DeFlock counter      : us={counts.get('us')} "
              f"worldwide={counts.get('worldwide')}")
    except Exception as exc:  # noqa: BLE001
        print(f"DeFlock counter      : unavailable ({exc})")

    print("\nPer-country (local vs live Overpass area query):")
    worst = 0.0
    for cc, n_local in sorted(local_by_country.items(), key=lambda x: -x[1]):
        if cc == "(none)":
            continue
        live = client.count(
            f'area["ISO3166-1"="{cc}"]["admin_level"="2"]->.a;'
            + node_way.replace("{scope}", "(area.a)")
        )
        drift = abs(n_local - live) / live if live else 0.0
        worst = max(worst, drift)
        flag = "  <-- CHECK" if drift > 0.10 else ""
        print(f"  {cc}: local {n_local:>8,}   live {live:>8,}   drift {drift:>6.2%}{flag}")

    if worst > 0.10:
        print("\nWARNING: >10% drift in at least one country - "
              "the local snapshot is stale or partial.")
        return 1
    print("\nAll countries within 10% of live Overpass counts.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="alpr_pipeline", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT,
                   help="Identify yourself to Overpass; include a contact address.")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="collect a snapshot into the database")
    f.add_argument("--source", choices=["derived", "overpass", "deflock-regions"],
                   default="derived",
                   help="derived = 1 HTTP request (default); overpass = full raw tags")
    f.add_argument("--countries", nargs="+", default=["US", "CA"],
                   help="derived source only")
    f.add_argument("--bbox", nargs=4, type=float, metavar=("S", "W", "N", "E"),
                   help="overpass source only; scope the harvest to one box")
    f.add_argument("--region", choices=["us", "world"], default="us",
                   help="overpass seeding: 'us' uses proven US-shaped seed "
                        "cells (default); 'world' grids the globe")
    f.add_argument("--seed-step", type=float, default=10.0,
                   help="overpass seed cell size in degrees for --region world. "
                        "Large cells make the count probe time out; keep <=10")
    f.add_argument("--min-interval", type=float, default=1.0,
                   help="minimum seconds between Overpass requests")
    f.add_argument("--no-geo", action="store_true",
                   help="skip country/state reverse geocoding")
    f.add_argument("--no-wikidata", action="store_true",
                   help="skip resolving *:wikidata Q-IDs to vendor labels")
    f.add_argument("--export", action="store_true", help="export after fetching")
    f.add_argument("--format", nargs="+",
                   default=["csv", "parquet", "geojson"],
                   choices=["csv", "parquet", "geojson", "xlsx"])
    f.set_defaults(func=cmd_fetch)

    e = sub.add_parser("export", help="write flat files from the database")
    e.add_argument("--flock-only", action="store_true")
    e.add_argument("--country", metavar="CC",
                   help="restrict to one ISO country code, e.g. US. Appends the "
                        "code to the filename (alpr_cameras_us.csv)")
    e.add_argument("--format", nargs="+",
                   default=["csv", "parquet", "geojson"],
                   choices=["csv", "parquet", "geojson", "xlsx"])
    e.set_defaults(func=cmd_export)

    c = sub.add_parser("covariates",
                       help="join census geography + ACS covariates")
    c.add_argument("--level", default="tract",
                   choices=["county", "place", "tract", "bg"],
                   help="unit of analysis (default: tract)")
    c.add_argument("--also-assign", nargs="*",
                   default=["county", "place"],
                   choices=["county", "place", "tract", "bg"],
                   help="additionally tag each camera with these GEOIDs")
    c.add_argument("--year", type=int, default=2023,
                   help="ACS 5-year vintage (end year)")
    c.add_argument("--refresh", action="store_true",
                   help="re-download ACS tables instead of using the cache")
    c.add_argument("--political", action="store_true",
                   help="add VEST reallocated election returns (tract/bg) and "
                        "American Ideology Project ideology. Fully anonymous.")
    c.add_argument("--crime", action="store_true",
                   help="add FBI UCR crime rates. DISCLOSES your identity to "
                        "Harvard Dataverse via a guestbook; requires --name, "
                        "--email, --institution and --research-question.")
    c.add_argument("--crime-year", type=int, default=2023,
                   help="UCR vintage (2019-2023)")
    c.add_argument("--name", help="guestbook: your name (disclosed)")
    c.add_argument("--email", help="guestbook: your email (disclosed)")
    c.add_argument("--institution",
                   help="guestbook: your institution (disclosed)")
    c.add_argument("--research-question",
                   help="guestbook: your research question, disclosed verbatim")
    c.add_argument("--format", nargs="+", default=["csv", "parquet"],
                   choices=["csv", "parquet"])
    c.set_defaults(func=cmd_covariates)

    s = sub.add_parser("summary", help="print dataset statistics")
    s.set_defaults(func=cmd_summary)

    v = sub.add_parser("verify", help="cross-check against live upstream counts")
    v.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
