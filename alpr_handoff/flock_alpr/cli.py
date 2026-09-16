"""Command line entrypoint: python -m flock_alpr <stage>"""
import argparse
import json
import sys

from . import config

STAGES = ("osm", "history", "aos", "geocode", "covariates", "panel", "all")


def _county_bpolys(states=None, max_regions=None):
    """Build a GeoJSON FeatureCollection of county polygons for ohsome."""
    from . import geocode

    counties = geocode.load_shapes("county")
    if states:
        fips = {config.STATE_FIPS[s] for s in states}
        counties = counties[counties["county_fips"].str[:2].isin(fips)]
    if max_regions:
        counties = counties.head(max_regions)

    counties = counties.copy()
    counties["geometry"] = counties.geometry.simplify(0.005)
    fc = json.loads(counties.to_json())
    for feat, cid in zip(fc["features"], counties["county_fips"]):
        feat["id"] = cid
        feat["properties"] = {"id": cid}
    return fc


def main(argv=None):
    p = argparse.ArgumentParser(prog="flock_alpr")
    p.add_argument("stage", choices=STAGES)
    p.add_argument("--states", nargs="*", default=None,
                   help="restrict to these USPS state codes")
    p.add_argument("--force", action="store_true", help="bypass the response cache")
    p.add_argument("--max-regions", type=int, default=None,
                   help="cap ohsome regions (for smoke tests)")
    args = p.parse_args(argv)

    if args.stage in ("osm", "all"):
        from . import extract_osm
        print("== Stage 1: Overpass ALPR nodes")
        extract_osm.run(states=args.states, force=args.force)

    if args.stage in ("aos", "all"):
        from . import extract_aos
        print("== Stage 3: Atlas of Surveillance")
        extract_aos.run(force=args.force)

    if args.stage in ("geocode", "all"):
        from . import geocode
        print("== Stage 4: spatial join")
        geocode.run(force=args.force)

    if args.stage in ("history", "all"):
        from . import extract_osm_history
        print("== Stage 2: ohsome discovery series")
        bpolys = _county_bpolys(args.states, args.max_regions)
        print(f"  {len(bpolys['features'])} county polygons")
        extract_osm_history.run(bpolys, force=args.force)

    if args.stage in ("covariates", "all"):
        from . import covariates
        print("== Stage 5: ACS + crime covariates")
        try:
            covariates.run(force=args.force)
        except RuntimeError as exc:
            print(f"  SKIPPED: {exc}", file=sys.stderr)

    if args.stage in ("panel", "all"):
        from . import build_panel
        print("== Stage 6: panel assembly")
        build_panel.run()


if __name__ == "__main__":
    main()
