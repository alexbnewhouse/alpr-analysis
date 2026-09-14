"""Tests for snapshot/upsert semantics.

The behaviour that matters here: re-running a *partial* source (the derived
feeds, which publish a display whitelist) must not wipe the raw tags, changeset
IDs, and usernames left by a *complete* source (an Overpass harvest).
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpr_pipeline.store import CameraStore  # noqa: E402


def check(label, got, want):
    status = "ok  " if got == want else "FAIL"
    if got != want:
        check.failures += 1
    print(f"  [{status}] {label}: got={got!r} want={want!r}")


check.failures = 0


def _rich_record():
    return {
        "osm_type": "node", "osm_id": 1, "lat": 40.0, "lon": -105.0,
        "brand_raw": "Flock Safety", "vendor": "Flock Safety", "is_flock": True,
        "osm_changeset": 12345, "osm_user": "mapper", "osm_uid": 99,
        "tag_count": 11, "tags_json": {"man_made": "surveillance"},
        "country_code": "US", "state": "CO",
        "manufacturer_wikidata": "Q108485435",
    }


def _thin_record():
    """What a derived feed produces: same camera, most columns absent."""
    return {
        "osm_type": "node", "osm_id": 1, "lat": 40.0, "lon": -105.0,
        "brand_raw": "Flock Safety", "vendor": "Flock Safety", "is_flock": True,
        "osm_changeset": None, "osm_user": None, "osm_uid": None,
        "tag_count": None, "tags_json": None,
        "country_code": "US", "state": "CO",
        "manufacturer_wikidata": None,
    }


def test_partial_source_preserves_rich_columns():
    print("\n-- partial source must not wipe a complete harvest")
    with tempfile.TemporaryDirectory() as td:
        store = CameraStore(Path(td) / "t.sqlite")

        s1 = store.begin_snapshot("overpass")
        store.write_records(s1, [_rich_record()], complete=True)
        store.finish_snapshot(s1, 1, 1)

        s2 = store.begin_snapshot("derived_feed")
        store.write_records(s2, [_thin_record()], complete=False)
        store.finish_snapshot(s2, 1, 1)

        row = store.conn.execute("SELECT * FROM cameras").fetchone()
        check("tags_json survived", row["tags_json"] is not None, True)
        check("osm_user survived", row["osm_user"], "mapper")
        check("osm_changeset survived", row["osm_changeset"], 12345)
        check("wikidata survived", row["manufacturer_wikidata"], "Q108485435")
        check("first_seen preserved", row["first_seen_snapshot"], s1)
        check("last_seen advanced", row["last_seen_snapshot"], s2)
        store.close()


def test_complete_source_overwrites():
    print("\n-- complete source must clear tags removed upstream")
    with tempfile.TemporaryDirectory() as td:
        store = CameraStore(Path(td) / "t.sqlite")

        s1 = store.begin_snapshot("overpass")
        store.write_records(s1, [_rich_record()], complete=True)
        store.finish_snapshot(s1, 1, 1)

        # Same camera, but the operator tag was deleted in OSM.
        cleared = _rich_record()
        cleared["osm_user"] = None
        s2 = store.begin_snapshot("overpass")
        store.write_records(s2, [cleared], complete=True)
        store.finish_snapshot(s2, 1, 1)

        row = store.conn.execute("SELECT * FROM cameras").fetchone()
        check("removed tag cleared", row["osm_user"], None)
        store.close()


def test_malformed_records_skipped():
    print("\n-- malformed records are skipped, not fatal")
    with tempfile.TemporaryDirectory() as td:
        store = CameraStore(Path(td) / "t.sqlite")
        s1 = store.begin_snapshot("derived_feed")
        bad = [
            {"osm_type": "node", "osm_id": None, "lat": 1.0, "lon": 2.0},
            {"osm_type": "node", "osm_id": 2, "lat": None, "lon": 2.0},
            _rich_record(),
        ]
        result = store.write_records(s1, bad, complete=False)
        check("wrote only the good record", result["records"], 1)
        check("counted 2 skipped", result["skipped"], 2)
        check("table has 1 row",
              store.conn.execute("SELECT COUNT(*) FROM cameras").fetchone()[0], 1)
        store.close()


def test_summary_latest_only():
    print("\n-- latest_only excludes cameras gone from the newest snapshot")
    with tempfile.TemporaryDirectory() as td:
        store = CameraStore(Path(td) / "t.sqlite")

        a, b = _rich_record(), _rich_record()
        b["osm_id"] = 2
        s1 = store.begin_snapshot("overpass")
        store.write_records(s1, [a, b], complete=True)
        store.finish_snapshot(s1, 2, 2)

        # Camera 2 disappeared from OSM.
        s2 = store.begin_snapshot("overpass")
        store.write_records(s2, [a], complete=True)
        store.finish_snapshot(s2, 1, 1)

        check("cumulative total", store.summary()["total"], 2)
        check("latest-only total", store.summary(latest_only=True)["total"], 1)
        store.close()


if __name__ == "__main__":
    test_partial_source_preserves_rich_columns()
    test_complete_source_overwrites()
    test_malformed_records_skipped()
    test_summary_latest_only()
    print(f"\n{'ALL PASS' if not check.failures else str(check.failures) + ' FAILURES'}")
    sys.exit(1 if check.failures else 0)
