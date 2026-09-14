"""Tests for covariate definitions and panel construction.

The ACS measure definitions are the easiest place in this pipeline to be
confidently wrong: a mistyped column index still produces numbers, and those
numbers still look like percentages. These check the invariants that would
catch such a slip.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpr_pipeline.covariates.pipeline import build_panel  # noqa: E402
from alpr_pipeline.covariates.variables import (  # noqa: E402
    MEASURES,
    SUMMARY_LEVELS,
    tables_needed,
)


def check(label, got, want):
    status = "ok  " if got == want else "FAIL"
    if got != want:
        check.failures += 1
    print(f"  [{status}] {label}: got={got!r} want={want!r}")


check.failures = 0


def test_measure_definitions():
    print("\n-- measure definitions")
    names = [m.name for m in MEASURES]
    check("no duplicate measure names", len(names), len(set(names)))

    # A ratio measure whose denominator is not in its own table would be
    # silently mis-scaled.
    bad_scale = [
        m.name for m in MEASURES
        if m.is_ratio and m.scale != 100.0
    ]
    check("all ratios scale to percent", bad_scale, [])

    # Non-ratio measures are levels (dollars, years, index) and must not be
    # multiplied by 100.
    bad_level = [m.name for m in MEASURES if not m.is_ratio and m.scale != 1.0]
    check("all levels scale by 1", bad_level, [])

    # Every column a measure references must be well-formed.
    malformed = [
        c for m in MEASURES for c in m.columns()
        if not c.startswith(m.table + "_E") or len(c.split("_E")[1]) != 3
    ]
    check("all column ids well-formed", malformed, [])

    check("measure count", len(MEASURES), 21)


def test_tables_needed():
    print("\n-- tables_needed")
    needed = tables_needed()
    # B02001 supplies five race shares plus the shared denominator.
    check("B02001 columns", sorted(needed["B02001"]),
          ["B02001_E001", "B02001_E002", "B02001_E003", "B02001_E004",
           "B02001_E005", "B02001_E008"])
    # B23025's denominator is the civilian labour force (E003), NOT E001.
    check("B23025 uses E003 denominator", sorted(needed["B23025"]),
          ["B23025_E003", "B23025_E005"])
    # pct_no_vehicle sums owner (E003) and renter (E010) no-vehicle counts.
    check("B25044 columns", sorted(needed["B25044"]),
          ["B25044_E001", "B25044_E003", "B25044_E010"])
    check("distinct tables", len(needed), 16)


def test_summary_levels():
    print("\n-- summary levels")
    for key, sl in SUMMARY_LEVELS.items():
        check(f"{key} code is 7 chars", len(sl.code), 7)
    check("tract fips length", SUMMARY_LEVELS["tract"].fips_length, 11)
    check("bg fips length", SUMMARY_LEVELS["bg"].fips_length, 12)
    check("county fips length", SUMMARY_LEVELS["county"].fips_length, 5)


def test_panel_keeps_zero_camera_geographies():
    print("\n-- panel includes zero-camera geographies")
    covariates = pd.DataFrame({
        "geoid": ["A", "B", "C"],
        "pop_total": [1000.0, 2000.0, 0.0],
    })
    cameras = pd.DataFrame({
        "osm_id": [1, 2, 3],
        "is_flock": [1, 1, 0],
        "geoid_tract": ["A", "A", "B"],
    })

    panel = build_panel(cameras, covariates, "tract")

    check("all geographies retained", len(panel), 3)
    check("zero-camera row present", int(panel.loc[panel.geoid == "C",
                                                   "camera_count"].iloc[0]), 0)
    check("counts correct", panel.set_index("geoid")["camera_count"].to_dict(),
          {"A": 2, "B": 1, "C": 0})
    check("flock counts correct",
          panel.set_index("geoid")["flock_count"].to_dict(),
          {"A": 2, "B": 0, "C": 0})
    check("has_camera flag", panel.set_index("geoid")["has_camera"].to_dict(),
          {"A": 1, "B": 1, "C": 0})
    # Zero-population geography must not produce inf cameras-per-capita.
    check("no inf per-capita",
          bool(panel["cameras_per_10k"].isin([float("inf")]).any()), False)
    check("zero-pop per-capita is null",
          bool(pd.isna(panel.loc[panel.geoid == "C", "cameras_per_10k"].iloc[0])),
          True)


def test_panel_drops_unassigned_cameras():
    print("\n-- cameras with no geography are excluded, not counted as a group")
    covariates = pd.DataFrame({"geoid": ["A"], "pop_total": [100.0]})
    cameras = pd.DataFrame({
        "osm_id": [1, 2],
        "is_flock": [1, 1],
        "geoid_tract": ["A", None],
    })
    panel = build_panel(cameras, covariates, "tract")
    check("only assigned camera counted", int(panel["camera_count"].sum()), 1)


if __name__ == "__main__":
    test_measure_definitions()
    test_tables_needed()
    test_summary_levels()
    test_panel_keeps_zero_camera_geographies()
    test_panel_drops_unassigned_cameras()
    print(f"\n{'ALL PASS' if not check.failures else str(check.failures) + ' FAILURES'}")
    sys.exit(1 if check.failures else 0)
