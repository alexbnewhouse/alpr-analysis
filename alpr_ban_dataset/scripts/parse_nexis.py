"""Turn Nexis Uni .docx exports into candidate rows for the decision register.

    python external/parse_nexis.py ~/Downloads/q0_calibration_001-300.DOCX
    python external/parse_nexis.py external/source/nexis/*.DOCX

Writes external/source/nexis/nexis_candidates.csv -- a STAGING file, not the
register itself. The parser proposes; a human disposes. Nothing here should be
copied into alpr_decisions.csv without someone reading the underlying article,
because the two hard problems below are only partly solvable by machine.

WHAT THIS EXTRACTS RELIABLY
    headline, publication, publication date, section, word length, byline,
    and the body text. Nexis writes these in a fixed order after each
    "End of Document" separator, so they parse exactly.

WHAT IT ONLY GUESSES
    `city` / `state`. Nexis has no municipality field; the deciding city is
    named in the headline or the lead, if at all. We match TIGER place names
    against the headline first, then the lead paragraphs, and prefer a match
    in the state implied by the publication ("The Times-Union (Albany, NY)").
    A single-word city name that is also an English word -- Reading, Mobile,
    Hope -- is a frequent false positive, so candidates carry `city_conf`.

    `action`. Headline verbs map to the register vocabulary crudely: "pauses"
    is `suspended`, "terminate" is `canceled`. But a headline reading "council
    moves to ban" describes a motion, not a passed ordinance, and only the
    body distinguishes them. Treat `action` as a sorting aid.

RELEVANCE
    The calibration search returns much that is not a municipal decision:
    state legislation, officer-misconduct stories, opinion letters, wire
    translations into Spanish and Portuguese, and university police forces.
    Each is flagged in `drop_reason` rather than deleted, so the exclusions
    stay auditable and you can check the filter is not eating real cases.
"""
import csv
import re
import sys
from pathlib import Path

import docx
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from flock_alpr import config, geocode  # noqa: E402
from flock_alpr.place_police import _norm  # noqa: E402

# NOT place_police.PLACE_SUFFIX. That regex strips the bare word "city", which
# is right for matching "Springfield Police Department" to "Springfield city"
# but catastrophic here: it turns "Iowa City" into "IOWA", which then matches
# any article mentioning the state. Only the governmental parentheticals and
# consolidation phrases are stripped.
GOV_SUFFIX = re.compile(
    r"\s*\((balance|part)\)|\s+(metropolitan|consolidated|unified)\s+government",
    re.I)

OUT = HERE / "source" / "nexis" / "nexis_candidates.csv"
NAMES_CACHE = config.INTERIM / "place_names.parquet"

STATES = {
 "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO",
 "Connecticut":"CT","Delaware":"DE","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID",
 "Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
 "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN",
 "Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV",
 "New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC",
 "North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA",
 "Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN","Texas":"TX",
 "Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV",
 "Wisconsin":"WI","Wyoming":"WY","District of Columbia":"DC"}
ABBR = set(STATES.values())

# Headline verb -> register vocabulary. Ordered: the first match wins, so the
# more specific patterns come first.
ACTION_PATTERNS = [
 (r"\bordinance\b|\bprohibit", "ordinance_ban"),
 (r"\bban(s|ned|ning)?\b|\breject(s|ed)?\b|\bvotes? (down|against)\b", "declined_to_adopt"),
 (r"\bpause|\bhalt|\bsuspend|\bon hold\b|\bmoratorium\b|\bturns? off\b|\bdeactivat", "suspended"),
 (r"\bnot renew|\bdoes ?n.t renew|\bnon-?renew|\blapse", "not_renewed"),
 (r"\bterminat|\bcancel|\bends?\b|\bscrap|\bdrops?\b|\bremov", "canceled"),
 (r"\bapprov|\badopt|\bexpand|\binstall|\brenews?\b|\bauthoriz", "adopted"),
]
REASON_PATTERNS = [
 (r"\bimmigration\b|\bICE\b|\bCBP\b|\bdeportat|\bfederal agenc", "federal_immigration_access"),
 (r"\bunauthoriz|\baudit\b|\bmisus|\bbreach\b", "unauthorized_access"),
 (r"\bprivacy\b|\bsurveillance\b|\bcivil liberties\b", "privacy"),
 (r"\bcost\b|\bbudget\b|\bexpensive\b", "cost"),
]
# Not municipal decisions. Flagged, never silently dropped.
DROP_PATTERNS = [
 (r"\bbill\b|\blegislat|\bstatewide\b|\bstate law\b|\bsenate\b|\bhouse (bill|panel)\b|"
  r"\bgeneral assembly\b|\bcongress", "state_or_federal_legislation"),
 (r"\bindicted\b|\baccused\b|\bmisus|\bresigns?\b|\bfired\b|\bcharged\b|\blawsuit\b|"
  r"\bstalking\b|\bex-girlfriend\b", "misconduct_or_litigation"),
 (r"^letter\b|\beditorial\b|\bopinion\b|\bcommentary\b|^instead of\b|\bmy turn\b", "opinion"),
 (r"\buniversity\b|\bcampus\b|\bUWPD\b|\bcollege\b", "university_police"),
 (r"\bcámaras\b|\bcamaras\b|\bvigilancia\b|\bciudades\b|\bempresa\b|\bmatrículas\b|"
  r"\bvigilância\b|\bcontrovérsia\b", "non_english"),
]

# Nexis carries Canadian papers, and "prohibited driver" is a Canadian traffic
# offence that the `prohibit!` search term matches on every occurrence. These
# are checked against publication + body, not just the headline.
CANADA_PATTERNS = re.compile(
 r"\bRCMP\b|\bOntario Provincial Police\b|\bOPP\b|\bOntario\b|\bQuebec\b|"
 r"\bSaskatchewan\b|\bAlberta\b|\bManitoba\b|\bBritish Columbia\b|\bNova Scotia\b|"
 r"\bNew Brunswick\b|\bNewfoundland\b|\bGuelph\b|\bToronto\b|\bWinnipeg\b|"
 r"\bCalgary\b|\bEdmonton\b|\bSaskatoon\b|\bMississauga\b|\bBrampton\b|"
 r"\bprohibited driver\b|\bCanadian\b|\bCanada\b", re.I)


def place_lookup() -> pd.DataFrame:
    """Normalised TIGER place names, cached after the first build."""
    if NAMES_CACHE.exists():
        return pd.read_parquet(NAMES_CACHE)
    import geopandas as gpd
    frames = []
    for st in config.STATES:
        fips = config.STATE_FIPS[st]
        p = geocode._cached_shapefile(
            f"{geocode.TIGER}/PLACE/tl_2024_{fips}_place.zip", f"place_{fips}.zip")
        g = gpd.read_file(f"zip://{p}", columns=["GEOID", "NAME", "geometry"])
        frames.append(pd.DataFrame({
            "place_geoid": g["GEOID"].astype(str).str.zfill(7),
            "name": g["NAME"], "state": st}))
    pl = pd.concat(frames, ignore_index=True)
    pl["norm"] = _norm(pl["name"].str.replace(GOV_SUFFIX, "", regex=True))
    pl = pl[pl["norm"].str.len() > 2]
    # Population is the tiebreak when a name repeats across states: an article
    # saying "Los Angeles" means California, not the Texas hamlet, and
    # "New Bedford" means Massachusetts, not Pennsylvania.
    try:
        pop = pd.read_parquet(HERE / "data" / "model_frame_place.parquet")[
            ["place_geoid", "population"]]
        pl = pl.merge(pop, on="place_geoid", how="left")
    except Exception:
        pl["population"] = 0.0
    pl["population"] = pl["population"].fillna(0.0)
    NAMES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    pl.to_parquet(NAMES_CACHE, index=False)
    return pl


def split_documents(path: Path):
    """Yield one list of paragraphs per article, skipping the table of contents."""
    ps = [p.text.rstrip() for p in docx.Document(str(path)).paragraphs]
    n = None
    for p in ps[:40]:
        m = re.match(r"\s*Documents\s*\((\d+)\)", p)
        if m:
            n = int(m.group(1)); break
    start = 0
    if n:                                   # skip past the final TOC entry
        for i, p in enumerate(ps):
            if re.match(rf"\s*{n}\.\s+\S", p):
                start = i + 1; break
    cur = []
    for p in ps[start:]:
        if "End of Document" in p:
            if cur: yield cur
            cur = []
        else:
            cur.append(p)
    if cur: yield cur


DATE_RE = re.compile(
    r"^\s*(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),\s+(\d{4})")
MONTHS = {m: f"{i+1:02d}" for i, m in enumerate(
 ["January","February","March","April","May","June","July","August","September",
  "October","November","December"])}


def parse_document(para):
    """Pull Nexis's fixed header fields, then the body."""
    lines = [p.strip() for p in para if p.strip()]
    if not lines:
        return None
    rec = {"headline": lines[0], "publication": "", "pub_date": "",
           "section": "", "length": "", "byline": "", "body": "", "url": ""}
    # Web-based items carry no date line but do carry the article URL, which
    # is the source link the register wants. Print items carry a date and no
    # URL. Handle both rather than assuming the print layout.
    for ln in lines[1:10]:
        if ln.startswith("http") and not rec["url"]:
            rec["url"] = ln.split()[0].rstrip(",;")
    for ln in lines[1:8]:
        if ln.startswith("http") or ln.strip() in ("WebNews - English", "University Wire"):
            continue
        m = DATE_RE.match(ln)
        if m and not rec["pub_date"]:
            rec["pub_date"] = f"{m.group(3)}-{MONTHS[m.group(1)]}-{int(m.group(2)):02d}"
            continue
        if not rec["publication"] and not m and not ln.lower().startswith(
                ("copyright", "section:", "length:", "byline:", "body")):
            rec["publication"] = ln
    for ln in lines:
        for key, pre in (("section", "Section:"), ("length", "Length:"), ("byline", "Byline:")):
            if ln.startswith(pre) and not rec[key]:
                rec[key] = ln[len(pre):].strip()
    # Web items have no publication date line; Nexis still stamps a Load-Date,
    # which is within a day or two of publication and is better than nothing.
    if not rec["pub_date"]:
        for ln in lines:
            if ln.startswith("Load-Date:"):
                m = DATE_RE.match(ln[len("Load-Date:"):].strip())
                if m:
                    rec["pub_date"] = f"{m.group(3)}-{MONTHS[m.group(1)]}-{int(m.group(2)):02d}"
                    rec["date_is_loaddate"] = True
                break
    if "Body" in lines:
        i = lines.index("Body")
        body = lines[i + 1:]
        body = [b for b in body if not b.startswith("Load-Date:")]
        rec["body"] = " ".join(body)
    return rec


def state_hint(publication, body):
    """Best guess at the state, from the publication's parenthetical or the text."""
    m = re.search(r"\(([^)]*,\s*([A-Z]{2}))\)", publication)
    if m and m.group(2) in ABBR:
        return m.group(2)
    for full, ab in STATES.items():
        if re.search(rf"\b{re.escape(full)}\b", publication):
            return ab
    for full, ab in STATES.items():
        if re.search(rf"\b{re.escape(full)}\b", body[:400]):
            return ab
    return ""


# Place names that are ordinary English words, or that contain a state name.
# Every one of these produced a false positive in the calibration batch:
# "Why, AZ" from "Why hundreds of cities", "Reader, WV" from "plate reader",
# "Texas City, TX" from "Tiny Texas town", "Iowa City, IA" from "in Iowa".
# NOTE _norm() upper-cases, so these are compared upper-cased below.
NAME_STOPLIST_RAW = {
 "why", "reader", "readers", "agency", "agency village", "hope", "mobile",
 "reading", "normal", "enterprise", "surprise", "boring", "sandwich", "index",
 "eight", "many", "friendly", "protection", "camera", "new city", "the city",
 "national", "federal", "union", "liberty", "american", "george", "police",
 "sheriff", "county line", "center", "centre", "north", "south", "east", "west",
 # Found in the calibration batch: each is a real municipality whose name is
 # also a common word or a state-plus-noun that matches ordinary prose.
 "the village", "man", "vincent", "garrett", "texas city", "iowa city",
 "new city", "california city", "nevada city", "kansas city city", "eight mile",
 "what cheer", "between", "only", "home", "rising", "goodwill", "hazard",
 "mass city", "lost city", "surprise", "hurricane", "sun city", "star city",
 "central city", "valley city", "bay city", "city view", "village",
 # From the q2 batch: "Council, ID" matched every "City Council" headline,
 # "Effort, PA" matched "Effort continues", "Success, AR" matched "Success of
 # New Camera Technology", "California, MD" matched any mention of the state.
 "council", "effort", "success", "california", "mccrory", "meet", "delay",
 "energy", "commerce", "industry", "advance", "progress", "moody", "gay",
 "banning", "ashville", "marks", "moore", "central", "humboldt", "greene",
}
NAME_STOPLIST = {x.upper() for x in NAME_STOPLIST_RAW}
STATE_IN_NAME = re.compile(
 r"\b(" + "|".join(re.escape(s.lower()) for s in STATES) + r")\b")


# Boilerplate that names a company's home city rather than the deciding city.
# "Atlanta-based Flock Safety" appears in a large share of coverage; without
# this, Atlanta is proposed for articles about a town in Mississippi.
VENDOR_LOCATION = re.compile(
 r"\b(Atlanta|Georgia)[- ]?(based|headquartered)\b|"
 r"\bbased in Atlanta\b|\bFlock Safety,? (?:an? )?Atlanta\b", re.I)


def find_city(headline, body, pl, hint):
    """Match the longest TIGER place name appearing in headline, then lead.

    Longest-first matters: 'New Bedford' must beat 'Bedford', and 'East
    Bridgewater' must beat 'Bridgewater'.
    """
    for field in ("headline", "lead"):
        raw = headline if field == "headline" else body[:600]
        raw = VENDOR_LOCATION.sub(" ", raw)
        text = " " + _norm(pd.Series([raw]))[0] + " "
        cand = []
        for r in pl.itertuples():
            if r.norm in NAME_STOPLIST or f" {r.norm} " not in text:
                continue
            # "Texas City" and "Iowa City" match any article mentioning the
            # state. Admit them only when the publication is in that state.
            if STATE_IN_NAME.search(r.norm) and r.state != hint:
                continue
            in_state = (hint != "" and r.state == hint)
            # Rank: state agreement first, then longer names ("New Bedford"
            # over "Bedford"), then population as the cross-state tiebreak.
            cand.append((in_state, len(r.norm), r.population, r.name, r.state, r.place_geoid))
        if cand:
            cand.sort(reverse=True)
            in_state, _, _, name, st, geoid = cand[0]
            if field == "headline":
                conf = "high" if in_state else "medium"
            else:
                conf = "low"
            return name, st, geoid, conf
    return "", hint, "", "none"


VOTE_RE = re.compile(
 r"\b(?:voted?|passed|approved|rejected|failed)[^.]{0,40}?\b(\d{1,2})\s*[-–to]{1,3}\s*(\d{1,2})\b"
 r"|\b(\d{1,2})\s*[-–]\s*(\d{1,2})\s+vote\b", re.I)
UNANIMOUS_RE = re.compile(r"\bunanimous(ly)?\b", re.I)


def find_vote(text):
    """Pull a council vote tally, e.g. 'passed 5-2' or 'by a 22-14 vote'.

    Returns (for, against, note). A unanimous vote has no tally to extract, so
    it is recorded as a note rather than invented numbers.
    """
    m = VOTE_RE.search(text)
    if m:
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        # Guard against years and dollar figures caught by the digit pattern.
        if int(a) <= 30 and int(b) <= 30:
            return a, b, ""
    if UNANIMOUS_RE.search(text):
        return "", "", "unanimous"
    return "", "", ""


def classify(text, table):
    for pat, lab in table:
        if re.search(pat, text, re.I):
            return lab
    return ""


def run(paths):
    pl = place_lookup()
    rows, seen = [], set()
    for path in paths:
        for para in split_documents(Path(path)):
            rec = parse_document(para)
            if not rec:
                continue
            hl, body = rec["headline"], rec["body"]
            hint = state_hint(rec["publication"], body)
            city, st, geoid, conf = find_city(hl, body, pl, hint)
            vote = find_vote(hl + " " + body[:1500])
            drop = classify(hl, DROP_PATTERNS)
            if not drop and CANADA_PATTERNS.search(rec["publication"] + " " + hl + " " + body[:600]):
                drop = "canadian"
            key = (hl.lower()[:90], rec["pub_date"])
            rows.append(dict(
                city=city, state=st, place_geoid=geoid, city_conf=conf,
                action=classify(hl, ACTION_PATTERNS),
                decision_date="", action_date="", adopted_date="", body="",
                vote_for=vote[0], vote_against=vote[1],
                reason=classify(hl + " " + body[:800], REASON_PATTERNS),
                reversed="", reversal_date="", source_type="news",
                source_url=rec.get("url", ""), verified="FALSE",
                drop_reason=drop, duplicate="TRUE" if key in seen else "FALSE",
                vote_note=vote[2],
                pub_date=rec["pub_date"], publication=rec["publication"],
                headline=hl, notes=body[:300], source_file=Path(path).name))
            seen.add(key)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    df = pd.DataFrame(rows)
    live = df[(df.drop_reason == "") & (df.duplicate == "FALSE")]
    print(f"  documents parsed        : {len(df):,}")
    print(f"  duplicate headlines     : {(df.duplicate == 'TRUE').sum():,}")
    print(f"  flagged not-a-decision  : {(df.drop_reason != '').sum():,}")
    for r, c in df[df.drop_reason != ""].drop_reason.value_counts().items():
        print(f"      {r:32s} {c:4d}")
    print(f"  LIVE candidates         : {len(live):,}")
    print(f"  ... with a city matched : {(live.city != '').sum():,}")
    print(f"  distinct cities         : {live.loc[live.city != '', 'city'].nunique():,}")
    print(f"\n  city match confidence: {live.city_conf.value_counts().to_dict()}")
    print(f"  action guess: {live.action.value_counts().to_dict()}")
    print(f"\n  -> {OUT}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: python external/parse_nexis.py <file.docx> [...]")
    run(args)
