"""SQLite storage with longitudinal snapshot tracking, plus flat-file exports.

Schema:
  snapshots     one row per pipeline run (provenance, counts, source)
  cameras       current state of every camera ever seen, with first/last seen
  observations  per-snapshot sighting of each camera - lets you measure
                deployment growth, removals, and relocations over time

The observations table is what makes this useful beyond a point-in-time dump:
re-run the pipeline weekly and you can query when a camera appeared, when it
vanished, and whether its coordinates or operator changed.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# Column order is the export order for CSV/Parquet/Excel too.
CAMERA_COLUMNS = [
    "osm_type", "osm_id", "lat", "lon",
    "country_code", "state",
    "brand_raw", "manufacturer_raw", "operator_raw",
    "brand_wikidata", "manufacturer_wikidata", "operator_wikidata",
    "vendor", "vendor_wikidata", "is_flock",
    "direction_raw", "direction_deg", "direction_count", "directions_all",
    "surveillance_zone", "surveillance_kind", "mount_type", "camera_type",
    "support", "height", "ref", "start_date", "operator_type",
    "description", "note", "website", "wikimedia_commons",
    "osm_version", "osm_timestamp", "osm_changeset", "osm_user", "osm_uid",
    "tag_count", "tags_json",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    started_utc       TEXT NOT NULL,
    finished_utc      TEXT,
    source            TEXT NOT NULL,
    endpoint          TEXT,
    osm_base_utc      TEXT,
    record_count      INTEGER,
    flock_count       INTEGER,
    notes             TEXT
);

CREATE TABLE IF NOT EXISTS cameras (
    osm_type          TEXT NOT NULL,
    osm_id            INTEGER NOT NULL,
    lat               REAL NOT NULL,
    lon               REAL NOT NULL,
    country_code      TEXT,
    state             TEXT,
    brand_raw         TEXT,
    manufacturer_raw  TEXT,
    operator_raw      TEXT,
    brand_wikidata    TEXT,
    manufacturer_wikidata TEXT,
    operator_wikidata TEXT,
    vendor            TEXT,
    vendor_wikidata   TEXT,
    is_flock          INTEGER,
    direction_raw     TEXT,
    direction_deg     REAL,
    direction_count   INTEGER,
    directions_all    TEXT,
    surveillance_zone TEXT,
    surveillance_kind TEXT,
    mount_type        TEXT,
    camera_type       TEXT,
    support           TEXT,
    height            TEXT,
    ref               TEXT,
    start_date        TEXT,
    operator_type     TEXT,
    description       TEXT,
    note              TEXT,
    website           TEXT,
    wikimedia_commons TEXT,
    osm_version       INTEGER,
    osm_timestamp     TEXT,
    osm_changeset     INTEGER,
    osm_user          TEXT,
    osm_uid           INTEGER,
    tag_count         INTEGER,
    tags_json         TEXT,
    first_seen_snapshot INTEGER,
    last_seen_snapshot  INTEGER,
    PRIMARY KEY (osm_type, osm_id)
);

CREATE TABLE IF NOT EXISTS observations (
    snapshot_id  INTEGER NOT NULL,
    osm_type     TEXT NOT NULL,
    osm_id       INTEGER NOT NULL,
    lat          REAL NOT NULL,
    lon          REAL NOT NULL,
    vendor       TEXT,
    is_flock     INTEGER,
    PRIMARY KEY (snapshot_id, osm_type, osm_id)
);

CREATE INDEX IF NOT EXISTS idx_cameras_latlon   ON cameras(lat, lon);
CREATE INDEX IF NOT EXISTS idx_cameras_vendor   ON cameras(vendor);
CREATE INDEX IF NOT EXISTS idx_cameras_flock    ON cameras(is_flock);
CREATE INDEX IF NOT EXISTS idx_cameras_state    ON cameras(country_code, state);
CREATE INDEX IF NOT EXISTS idx_cameras_operator ON cameras(operator_raw);
CREATE INDEX IF NOT EXISTS idx_obs_camera       ON observations(osm_type, osm_id);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _schema_column_types() -> dict[str, str]:
    """Parse the `cameras` column declarations out of SCHEMA.

    Derived from SCHEMA rather than duplicated, so a column can never be added
    to the table definition and forgotten in the migration path.
    """
    body = SCHEMA.split("CREATE TABLE IF NOT EXISTS cameras (", 1)[1]
    body = body.split(");", 1)[0]
    types: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith("PRIMARY KEY"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            types[parts[0]] = " ".join(parts[1:])
    return types


class CameraStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add any columns missing from a database created by an older version.

        `CREATE TABLE IF NOT EXISTS` silently leaves an existing table alone, so
        without this an upgraded pipeline would fail on the first insert against
        a pre-existing DB.
        """
        existing = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(cameras)")
        }
        wanted = _schema_column_types()
        for col, decl in wanted.items():
            if col not in existing:
                # SQLite rejects ADD COLUMN ... NOT NULL without a default, and
                # a back-filled column has no value for existing rows anyway.
                decl = decl.replace("NOT NULL", "").strip()
                log.info("Migrating: adding cameras.%s", col)
                self.conn.execute(f"ALTER TABLE cameras ADD COLUMN {col} {decl}")

    def close(self) -> None:
        self.conn.close()

    def begin_snapshot(self, source: str, endpoint: str | None = None,
                       notes: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO snapshots (started_utc, source, endpoint, notes) "
            "VALUES (?, ?, ?, ?)",
            (_utcnow(), source, endpoint, notes),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def write_records(self, snapshot_id: int, records: list[dict],
                      complete: bool = True) -> dict:
        """Upsert records and record one observation each. Returns a summary.

        `complete` declares whether this source carries the full column set. An
        Overpass harvest does, so it overwrites everything — a tag deleted in
        OSM must be cleared here too. The derived feeds do not: they publish a
        display whitelist and hard-code the rest to None. Merging those with
        overwrite semantics would silently wipe the raw tags, changeset IDs, and
        usernames from a previous harvest, so for partial sources a NULL means
        "this feed doesn't carry that field" and the stored value is kept.
        """
        rows = []
        obs = []
        skipped = 0
        for rec in records:
            # A record missing its identity or position cannot be stored, and
            # letting it through aborts the whole batch on a NOT NULL violation.
            if (rec.get("osm_type") is None or rec.get("osm_id") is None
                    or rec.get("lat") is None or rec.get("lon") is None):
                skipped += 1
                continue
            tags = rec.get("tags_json")
            row = [rec.get(col) for col in CAMERA_COLUMNS]
            # tags_json is the last column; serialize the dict for storage.
            row[-1] = json.dumps(tags, sort_keys=True) if isinstance(tags, dict) else tags
            row = [int(v) if isinstance(v, bool) else v for v in row]
            rows.append((*row, snapshot_id, snapshot_id))
            obs.append((
                snapshot_id, rec["osm_type"], rec["osm_id"],
                rec["lat"], rec["lon"], rec.get("vendor"),
                int(bool(rec.get("is_flock"))),
            ))

        placeholders = ", ".join("?" * (len(CAMERA_COLUMNS) + 2))
        cols = ", ".join(CAMERA_COLUMNS)
        # On conflict, refresh attributes and extend last_seen, but keep the
        # original first_seen so the appearance date survives re-runs.
        if complete:
            updates = ", ".join(f"{c}=excluded.{c}" for c in CAMERA_COLUMNS)
        else:
            # Identity and position always come from the incoming row; every
            # other column falls back to what is already stored.
            always = {"osm_type", "osm_id", "lat", "lon"}
            updates = ", ".join(
                f"{c}=excluded.{c}" if c in always
                else f"{c}=COALESCE(excluded.{c}, cameras.{c})"
                for c in CAMERA_COLUMNS
            )

        self.conn.executemany(
            f"INSERT INTO cameras ({cols}, first_seen_snapshot, last_seen_snapshot) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT(osm_type, osm_id) DO UPDATE SET {updates}, "
            f"last_seen_snapshot=excluded.last_seen_snapshot",
            rows,
        )
        self.conn.executemany(
            "INSERT OR REPLACE INTO observations "
            "(snapshot_id, osm_type, osm_id, lat, lon, vendor, is_flock) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            obs,
        )
        self.conn.commit()

        if skipped:
            log.warning("Skipped %d record(s) missing identity or coordinates", skipped)
        flock = sum(1 for r in records if r.get("is_flock"))
        return {"records": len(rows), "flock": flock, "skipped": skipped}

    def finish_snapshot(self, snapshot_id: int, record_count: int,
                        flock_count: int, osm_base_utc: str | None = None) -> None:
        self.conn.execute(
            "UPDATE snapshots SET finished_utc=?, record_count=?, flock_count=?, "
            "osm_base_utc=? WHERE snapshot_id=?",
            (_utcnow(), record_count, flock_count, osm_base_utc, snapshot_id),
        )
        self.conn.commit()

    # --- reads -------------------------------------------------------------

    def dataframe(self, flock_only: bool = False, snapshot_id: int | None = None,
                  country: str | None = None):
        import pandas as pd

        sql = f"SELECT {', '.join(CAMERA_COLUMNS)}, first_seen_snapshot, " \
              f"last_seen_snapshot FROM cameras"
        clauses, params = [], []
        if flock_only:
            clauses.append("is_flock = 1")
        if country:
            clauses.append("country_code = ?")
            params.append(country)
        if snapshot_id is not None:
            clauses.append("last_seen_snapshot = ?")
            params.append(snapshot_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY osm_type, osm_id"
        return pd.read_sql_query(sql, self.conn, params=params)

    def summary(self, latest_only: bool = False) -> dict:
        """Dataset statistics.

        `latest_only` restricts to cameras seen in the most recent snapshot,
        which is what you want when comparing against a live upstream count:
        the full table is cumulative and includes cameras since removed from
        OSM, so it drifts upward forever.
        """
        c = self.conn
        where = ""
        if latest_only:
            where = (
                " WHERE last_seen_snapshot = "
                "(SELECT MAX(snapshot_id) FROM snapshots WHERE record_count IS NOT NULL)"
            )
        total = c.execute(f"SELECT COUNT(*) FROM cameras{where}").fetchone()[0]
        flock = c.execute(
            f"SELECT COUNT(*) FROM cameras{where}"
            + (" AND" if where else " WHERE") + " is_flock=1"
        ).fetchone()[0]
        by_vendor = c.execute(
            "SELECT COALESCE(vendor,'(unclassified)') v, COUNT(*) n FROM cameras"
            f"{where} GROUP BY v ORDER BY n DESC"
        ).fetchall()
        by_state = c.execute(
            "SELECT COALESCE(state,'(none)') s, COUNT(*) n FROM cameras"
            f"{where}" + (" AND" if where else " WHERE")
            + " country_code='US' GROUP BY s ORDER BY n DESC LIMIT 15"
        ).fetchall()
        by_country = c.execute(
            "SELECT COALESCE(country_code,'(none)') cc, COUNT(*) n FROM cameras"
            f"{where} GROUP BY cc ORDER BY n DESC LIMIT 15"
        ).fetchall()
        return {
            "total": total,
            "flock": flock,
            "by_vendor": [dict(r) for r in by_vendor],
            "by_state": [dict(r) for r in by_state],
            "by_country": [dict(r) for r in by_country],
        }


# --- exports ---------------------------------------------------------------

def export_all(store: CameraStore, out_dir: Path, flock_only: bool = False,
               formats: tuple[str, ...] = ("csv", "parquet", "geojson"),
               country: str | None = None) -> list[Path]:
    """Write the current camera table to flat files. Returns paths written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "flock_cameras" if flock_only else "alpr_cameras"
    if country:
        stem = f"{stem}_{country.lower()}"
    df = store.dataframe(flock_only=flock_only, country=country)
    written: list[Path] = []

    if "csv" in formats:
        path = out_dir / f"{stem}.csv"
        df.to_csv(path, index=False)
        written.append(path)

    if "parquet" in formats:
        path = out_dir / f"{stem}.parquet"
        # tags_json is a JSON string; keep it as such so the column stays typed.
        df.to_parquet(path, index=False)
        written.append(path)

    if "xlsx" in formats:
        path = out_dir / f"{stem}.xlsx"
        # Excel caps at 1,048,576 rows; the dataset is ~135k so this is safe,
        # but drop tags_json - it blows past Excel's 32,767-char cell limit.
        df.drop(columns=["tags_json"], errors="ignore").to_excel(path, index=False)
        written.append(path)

    if "geojson" in formats:
        path = out_dir / f"{stem}.geojson"
        _write_geojson(df, path)
        written.append(path)

    for p in written:
        log.info("wrote %s (%.1f MB)", p, p.stat().st_size / 1e6)
    return written


def _write_geojson(df, path: Path) -> None:
    """Stream a FeatureCollection so we never hold two copies in memory."""
    import math

    skip = {"lat", "lon"}
    cols = [c for c in df.columns if c not in skip]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"type":"FeatureCollection","features":[\n')
        for i, row in enumerate(df.itertuples(index=False)):
            d = dict(zip(df.columns, row))
            props = {}
            for k in cols:
                v = d[k]
                if v is None:
                    continue
                if isinstance(v, float) and math.isnan(v):
                    continue
                props[k] = v
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [float(d["lon"]), float(d["lat"])]},
                "properties": props,
            }
            fh.write(("," if i else "") + json.dumps(feature, default=str) + "\n")
        fh.write("]}\n")
