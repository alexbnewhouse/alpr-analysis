"""Tag normalization: direction parsing and vendor/brand classification.

Direction parsing is a faithful port of FlockHopper's `parseDirections`
(worker/src/fetchers/cameras.ts), so values here line up with what
maps.deflock.org renders. Vendor classification is ours: OSM brand strings are
free text and arrive as "Flock Safety", "Flock Group Inc.", "flocksafety", etc.
"""

from __future__ import annotations

import re

CARDINALS: dict[str, float] = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}

SPELLED_CARDINALS: dict[str, float] = {
    "NORTH": 0, "NORTHEAST": 45, "EAST": 90, "SOUTHEAST": 135,
    "SOUTH": 180, "SOUTHWEST": 225, "WEST": 270, "NORTHWEST": 315,
}

# Travel-direction tags seen on highway-mounted cameras.
BOUND_DIRECTIONS: dict[str, float] = {"NB": 0, "EB": 90, "SB": 180, "WB": 270}

# A plain decimal number, optionally signed. Deliberately stricter than
# float(): no "nan", no "inf", no "1_0".
_NUMERIC_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")


def _normalize_degrees(deg: float) -> float:
    return ((deg % 360) + 360) % 360


def _resolve_simple(token: str) -> float | None:
    """Resolve a cardinal, spelled-out, bound, or numeric token to raw degrees."""
    upper = token.strip().upper()
    if not upper:
        return None
    if upper in CARDINALS:
        return CARDINALS[upper]
    if upper in SPELLED_CARDINALS:
        return SPELLED_CARDINALS[upper]
    if upper in BOUND_DIRECTIONS:
        return BOUND_DIRECTIONS[upper]
    # Full-string float match only, so "338-23" falls through to range handling
    # instead of being silently read as a negative number. Guard the strings
    # Python's float() accepts but a compass bearing never is: "nan", "inf",
    # and underscore separators like "1_0" (which would parse as 10).
    if not _NUMERIC_RE.match(upper):
        return None
    try:
        return float(upper)
    except ValueError:
        return None


def _range_midpoint(start_deg: float, end_deg: float) -> float:
    """Midpoint bearing of the clockwise sector from start to end."""
    raw_arc = end_deg - start_deg
    arc = ((raw_arc % 360) + 360) % 360
    if arc == 0 and raw_arc != 0:  # full circle, e.g. "0-360"
        return _normalize_degrees(start_deg + 180)
    if arc == 0:
        return _normalize_degrees(start_deg)
    return _normalize_degrees(start_deg + arc / 2)


def _parse_single_token(token: str) -> float | None:
    trimmed = token.strip()
    if not trimmed:
        return None

    simple = _resolve_simple(trimmed)
    if simple is not None:
        return _normalize_degrees(simple)

    # Range notation: "338-23", "WSW-ESE". Search from index 1 so a leading
    # minus sign is not mistaken for the range separator.
    dash_idx = trimmed.find("-", 1)
    if dash_idx > 0:
        left = _resolve_simple(trimmed[:dash_idx])
        right = _resolve_simple(trimmed[dash_idx + 1:])
        if left is not None and right is not None:
            return _range_midpoint(left, right)

    return None


def parse_directions(value: str | None) -> list[float]:
    """Parse a direction tag into every bearing it encodes.

    Handles multi-valued tags ("90;270" for a two-way gantry), cardinals,
    spelled-out names, bound notation, and ranges.
    """
    if not value:
        return []
    out: list[float] = []
    for token in re.split(r"[;,]", value):
        token = token.strip()
        if not token:
            continue
        deg = _parse_single_token(token)
        if deg is not None:
            out.append(deg)
    return out


# --- Vendor classification -------------------------------------------------
#
# Ordered: the first pattern to match wins, so more specific vendors precede
# the parent companies that acquired them (Vigilant -> Motorola, ELSAG ->
# Leonardo). Matched case-insensitively against brand, manufacturer, operator.

VENDOR_PATTERNS: list[tuple[str, str]] = [
    ("Flock Safety", r"\bflock\s*(safety|group|safey)?\b|\bflocksafety\b"),
    ("Motorola Solutions", r"\bmotorola\b|\bvigilant\s*(solutions)?\b|\bpips\b|\bl3\s*harris\b"),
    ("Genetec", r"\bgenetec\b|\bautovu\b"),
    ("Leonardo/ELSAG", r"\belsag\b|\bleonardo\b|\bselex\b"),
    ("Rekor", r"\brekor\b|\bopenalpr\b"),
    ("Ubicquia", r"\bubicquia\b|\bubicell\b"),
    ("Neology", r"\bneology\b"),
    ("Ekin", r"\bekin\b"),
    ("Axis Communications", r"\baxis\b"),
    ("Avigilon", r"\bavigilon\b"),
    ("Verra Mobility", r"\bverra\b|\bredflex\b|\bamerican traffic solutions\b|\bats\b"),
    ("Conduent", r"\bconduent\b"),
    ("Jenoptik", r"\bjenoptik\b|\bvysionics\b"),
    ("Tattile", r"\btattile\b"),
    ("Nedap", r"\bnedap\b"),
    ("Hikvision", r"\bhikvision\b"),
    ("Dahua", r"\bdahua\b"),
    ("Bosch", r"\bbosch\b"),
    ("Gatekeeper", r"\bgatekeeper\b"),
    ("Perceptics", r"\bperceptics\b"),
    ("Kapsch", r"\bkapsch\b"),
    ("Siemens", r"\bsiemens\b"),
    ("Q-Free", r"\bq-?free\b"),
    ("Nortech", r"\bnortech\b"),
    ("Vetted Security", r"\bvetted\b"),
    ("Insight LPR", r"\binsight\s*lpr\b"),
]

_COMPILED_VENDORS = [(name, re.compile(pat, re.I)) for name, pat in VENDOR_PATTERNS]

# Placeholder brand values that carry no vendor information.
_NULL_BRANDS = {
    "", "unknown", "unspecified", "n/a", "na", "none", "?", "-", "tbd",
    "yes", "no", "fixme", "unidentified", "not specified",
}


def classify_vendor(*candidates: str | None) -> str | None:
    """Return a canonical vendor name from free-text brand/manufacturer/operator.

    Candidates are tried in order; within each, the first matching pattern wins.
    Returns None when nothing matches (including for placeholder values).
    """
    for raw in candidates:
        if not raw:
            continue
        value = raw.strip()
        if value.lower() in _NULL_BRANDS:
            continue
        for name, pattern in _COMPILED_VENDORS:
            if pattern.search(value):
                return name
    return None


_FLOCK_RE = re.compile(r"\bflock\s*(safety|group|safey)?\b|\bflocksafety\b", re.I)

# Wikidata entity for Flock Safety, verified against the Wikidata API rather
# than assumed. An OSM `*:wikidata` tag carrying this is authoritative in a way
# free-text brand strings are not.
FLOCK_WIKIDATA = {"Q108485435"}


def is_flock_qid(*qids: str | None) -> bool:
    """True if any Wikidata Q-ID identifies Flock Safety."""
    return any(q and q.strip() in FLOCK_WIKIDATA for q in qids)


def is_flock(*candidates: str | None) -> bool:
    """True if any brand/manufacturer/operator string identifies Flock Safety.

    Deliberately checks operator too: many nodes carry `operator=Flock Safety`
    with no brand tag at all (Flock-owned deployments rather than agency-owned).
    """
    return any(c and _FLOCK_RE.search(c) for c in candidates)


def clean_str(value: str | None) -> str | None:
    """Trim whitespace and map placeholder values to None."""
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in _NULL_BRANDS:
        return None
    return value
