"""Tests for direction parsing and vendor classification.

Direction cases mirror FlockHopper's own test expectations so the two
implementations agree on the same OSM tag values.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpr_pipeline.normalize import (  # noqa: E402
    classify_vendor,
    clean_str,
    is_flock,
    parse_directions,
)


def check(label, got, want):
    status = "ok  " if got == want else "FAIL"
    if got != want:
        check.failures += 1
    print(f"  [{status}] {label}: got={got!r} want={want!r}")


check.failures = 0


def test_directions():
    print("\n-- parse_directions")
    check("numeric", parse_directions("270"), [270.0])
    check("cardinal N", parse_directions("N"), [0.0])
    check("cardinal WSW", parse_directions("WSW"), [247.5])
    check("spelled", parse_directions("northeast"), [45.0])
    check("bound NB", parse_directions("NB"), [0.0])
    check("bound WB", parse_directions("wb"), [270.0])
    check("multi semicolon", parse_directions("90;270"), [90.0, 270.0])
    check("multi comma", parse_directions("N,S"), [0.0, 180.0])
    check("wraparound normalize", parse_directions("450"), [90.0])
    check("negative normalize", parse_directions("-90"), [270.0])
    check("range numeric", parse_directions("338-23"), [0.5])
    # WSW(247.5) -> ESE(112.5) sweeps 225 deg clockwise *through north*,
    # so the midpoint is 0, not the 180 you get by averaging naively.
    check("range cardinal", parse_directions("WSW-ESE"), [0.0])
    check("range cardinal short way", parse_directions("ESE-WSW"), [180.0])
    check("full circle", parse_directions("0-360"), [180.0])
    check("empty", parse_directions(""), [])
    check("none", parse_directions(None), [])
    check("garbage", parse_directions("banana"), [])
    check("mixed valid/invalid", parse_directions("90;banana;180"), [90.0, 180.0])
    check("whitespace", parse_directions("  45  "), [45.0])
    check("float", parse_directions("22.5"), [22.5])


def test_vendor():
    print("\n-- classify_vendor / is_flock")
    check("flock safety", classify_vendor("Flock Safety"), "Flock Safety")
    check("flock group", classify_vendor("Flock Group Inc."), "Flock Safety")
    check("flock bare", classify_vendor("Flock"), "Flock Safety")
    check("flock lower", classify_vendor("flocksafety"), "Flock Safety")
    check("motorola", classify_vendor("Motorola Solutions"), "Motorola Solutions")
    check("vigilant->motorola", classify_vendor("Vigilant Solutions"),
          "Motorola Solutions")
    check("genetec", classify_vendor("Genetec"), "Genetec")
    check("autovu->genetec", classify_vendor("AutoVu"), "Genetec")
    check("elsag", classify_vendor("ELSAG"), "Leonardo/ELSAG")
    check("placeholder unknown", classify_vendor("Unknown"), None)
    check("placeholder yes", classify_vendor("yes"), None)
    check("none", classify_vendor(None), None)
    check("no match", classify_vendor("Acme Cameras"), None)
    check("falls through to operator",
          classify_vendor(None, None, "Flock Safety"), "Flock Safety")
    check("brand wins over operator",
          classify_vendor("Genetec", None, "Flock Safety"), "Genetec")

    check("is_flock brand", is_flock("Flock Safety"), True)
    check("is_flock operator only", is_flock(None, None, "Flock Safety"), True)
    check("is_flock negative", is_flock("Genetec", None, "Detroit PD"), False)
    check("is_flock none", is_flock(None, None, None), False)
    # Guard against substring false positives on unrelated words.
    check("is_flock not 'flocking'", is_flock("Flockhart Industries"), False)


def test_clean():
    print("\n-- clean_str")
    check("trim", clean_str("  Flock  "), "Flock")
    check("placeholder", clean_str("unknown"), None)
    check("empty", clean_str("   "), None)
    check("none", clean_str(None), None)
    check("keeps real", clean_str("Amarillo Police Department"),
          "Amarillo Police Department")


if __name__ == "__main__":
    test_directions()
    test_vendor()
    test_clean()
    print(f"\n{'ALL PASS' if not check.failures else str(check.failures) + ' FAILURES'}")
    sys.exit(1 if check.failures else 0)
