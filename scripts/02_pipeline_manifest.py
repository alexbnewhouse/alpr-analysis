#!/usr/bin/env python
"""Write alpr_pipeline/DATA_MANIFEST.md: an inventory of the gitignored
alpr_pipeline/data directory (sizes, row counts, columns, key summaries) so
the repo documents what exists without committing ~1 GB.

Run from the repo root:  .venv/bin/python scripts/02_pipeline_manifest.py
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

DATA = Path("alpr_pipeline/data")
OUT = Path("alpr_pipeline/DATA_MANIFEST.md")


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def parquet_info(p: Path) -> tuple[int, list[str]]:
    md = pq.read_metadata(p)
    return md.num_rows, pq.read_schema(p).names


def table(rows: list[list[str]], header: list[str]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


lines = [
    "# alpr_pipeline/data — manifest",
    "",
    f"Generated {date.today()} by `scripts/02_pipeline_manifest.py`. The directory itself is "
    "gitignored (≈1 GB); on Alex's machine it is a symlink to `~/flock_research/alpr_pipeline/data`.",
    "",
    "## Files",
    "",
]

rows = []
for p in sorted(DATA.iterdir()):
    if p.is_dir():
        continue
    size = human(p.stat().st_size)
    if p.suffix == ".parquet":
        n, cols = parquet_info(p)
        rows.append([f"`{p.name}`", size, f"{n:,}", f"{len(cols)} cols"])
    elif p.suffix == ".sqlite":
        con = sqlite3.connect(p)
        tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
        counts = {t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in tabs}
        con.close()
        rows.append([f"`{p.name}`", size, ", ".join(f"{t}={c:,}" for t, c in counts.items()), "sqlite"])
    else:
        rows.append([f"`{p.name}`", size, "", p.suffix.lstrip(".")])
lines += table(rows, ["File", "Size", "Rows", "Type"])

lines += ["", "## Covariate cache (`data/cache/`)", ""]
rows = [[f"`{p.name}`", human(p.stat().st_size)] for p in sorted((DATA / "cache").iterdir())]
lines += table(rows, ["File", "Size"])

# ---- the modelling table ----------------------------------------------------
panel_path = DATA / "tract_panel.parquet"
if panel_path.exists():
    panel = pd.read_parquet(panel_path)
    n = len(panel)
    lines += [
        "",
        "## `tract_panel.parquet` — the modelling table",
        "",
        f"- **{n:,} tracts**; {panel['has_camera'].sum():,} with ≥1 camera "
        f"({panel['has_camera'].mean():.1%}); {int(panel['camera_count'].sum()):,} cameras, "
        f"{int(panel['flock_count'].sum()):,} Flock ({panel['flock_count'].sum() / panel['camera_count'].sum():.1%}).",
        f"- Camera count among adopters: median {panel.loc[panel.has_camera, 'camera_count'].median():.0f}, "
        f"mean {panel.loc[panel.has_camera, 'camera_count'].mean():.1f}, "
        f"max {panel['camera_count'].max():.0f}.",
        "- Columns:",
        "",
    ]
    for c in panel.columns:
        nn = panel[c].notna().mean()
        lines.append(f"  - `{c}` ({panel[c].dtype}, {nn:.0%} non-null)")

# ---- cameras -------------------------------------------------------------------
cam_path = DATA / "alpr_cameras_us.parquet"
if cam_path.exists():
    cams = pd.read_parquet(cam_path)
    lines += [
        "",
        "## `alpr_cameras_us.parquet` — the US camera master",
        "",
        f"- **{len(cams):,} cameras**; `is_flock` = {int(cams['is_flock'].sum()):,} "
        f"({cams['is_flock'].mean():.1%}); `osm_type = way` (mistagged roads) = "
        f"{(cams['osm_type'] == 'way').sum():,}.",
        f"- Vendors: " + ", ".join(
            f"{k} {v:,}" for k, v in cams["vendor"].fillna("(unknown)").value_counts().head(8).items()
        ) + ".",
        f"- Operator tag present: {cams['operator_raw'].notna().mean():.1%} of rows "
        "(the draft's 'majority do not have this information').",
        f"- Editor metadata (`osm_user`) present in this *derived* export: {cams['osm_user'].notna().mean():.1%}. "
        "The `overpass` harvest in `alpr_us_full.sqlite` (below) is where editor metadata lives.",
    ]

# ---- full overpass harvest -----------------------------------------------------
full = DATA / "alpr_us_full.sqlite"
if full.exists():
    con = sqlite3.connect(full)
    n, n_user, n_tags, n_editors = con.execute(
        "select count(*), sum(osm_user is not null), sum(tags_json is not null), count(distinct osm_user) from cameras"
    ).fetchone()
    snap = con.execute("select source, started_utc, osm_base_utc from snapshots").fetchall()
    con.close()
    lines += [
        "",
        "## `alpr_us_full.sqlite` — the full Overpass harvest",
        "",
        f"- **{n:,} cameras** with complete raw tags (`tags_json` on {n_tags:,}) and editor metadata "
        f"(`osm_user` on {n_user:,}; **{n_editors:,} distinct editors**). This is the source of "
        "`n_mappers` / `first_mapped` / `last_mapped` in the tract panel.",
        "- Snapshots: " + "; ".join(f"{s} at {t} (OSM base {b})" for s, t, b in snap) + ".",
    ]

OUT.write_text("\n".join(lines) + "\n")
print("\n".join(lines))
