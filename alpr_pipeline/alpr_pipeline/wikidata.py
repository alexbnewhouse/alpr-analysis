"""Resolve OSM `*:wikidata` Q-IDs to vendor labels, with a disk cache.

Many ALPR nodes carry `manufacturer:wikidata`, `brand:wikidata`, or
`operator:wikidata`. Those Q-IDs are unambiguous identifiers, which makes them
more reliable than the free-text `brand` field for vendor attribution -- OSM
contributors write "Flock Safety", "Flock Group Inc.", and "flocksafety" for the
same company, but they all point at Q108485435.

Two failure modes this module has to survive, both observed in the live data:

* **A typo'd Q-ID that is still a valid entity.** Q108485435 is Flock Safety;
  the data also contains Q1084854 (a person, Christoph Franck), Q108485385
  (another person), Q10485435 (a springtail species), and Q108485 (a third
  person). These resolve to real labels, so a naive lookup silently attributes
  a camera to "Doug Olds". Entities are therefore type-checked via P31 and
  rejected if they are humans or taxa.
* **A typo'd Q-ID that does not exist at all** (Q108485435340). `wbgetentities`
  rejects the *entire batch* when any one id is unknown, so one bad tag would
  cost every label in its batch. Batches are bisected to isolate the offender.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
QID_RE = re.compile(r"^Q\d+$")
BATCH_SIZE = 50  # wbgetentities accepts up to 50 ids per call

# Anonymous Wikidata API access is rate limited; space requests out.
MIN_INTERVAL = 1.0
MAX_RETRIES = 4

# P31 ("instance of") values that disqualify an entity from being a vendor.
# A camera's manufacturer is never a person or a biological taxon, so these
# indicate a mistyped Q-ID rather than an unusual company.
REJECT_INSTANCE_OF = {
    "Q5",        # human
    "Q16521",    # taxon
    "Q4167410",  # Wikimedia disambiguation page
    "Q13442814", # scholarly article
    "Q30612",    # clinical trial
    "Q41176",    # building
    "Q486972",   # human settlement
    "Q56061",    # administrative territorial entity
}

# This filter catches mistyped Q-IDs that land on an obviously-not-a-vendor
# entity. It cannot catch one that lands on a *different real company*
# (Genentech has appeared in a `manufacturer:wikidata` tag). So treat
# `vendor_wikidata` as "the entity the mapper linked", not as ground truth --
# compare it against the curated free-text `vendor` and investigate mismatches.


def valid_qid(value: str | None) -> str | None:
    """Return the Q-ID if `value` is a single well-formed one, else None."""
    if not value:
        return None
    v = value.strip()
    # Multi-valued tags ("Q1;Q2") are ambiguous for attribution -- skip them.
    return v if QID_RE.match(v) else None


class WikidataLabels:
    def __init__(self, cache_dir: Path):
        cache_dir = Path(cache_dir)
        self.cache_path = cache_dir / "wikidata_labels.json"
        self.rejected_path = cache_dir / "wikidata_rejected.json"
        self._cache: dict[str, str] = _load_json(self.cache_path, {})
        # {qid: reason} for ids that are permanently unusable. Distinct from a
        # transient failure, which must never be cached.
        self._rejected: dict[str, str] = _load_json(self.rejected_path, {})
        self._last_request = 0.0

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._cache, indent=1, sort_keys=True))
        self.rejected_path.write_text(
            json.dumps(self._rejected, indent=1, sort_keys=True)
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        self._last_request = time.monotonic()

    def _request(self, batch: list[str]) -> tuple[dict | None, bool]:
        """Return (payload, permanent_failure).

        `permanent_failure` is True only for a genuine "no such entity" -- a
        429 or 5xx is transient and must not poison the cache.
        """
        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                resp = requests.get(
                    WIKIDATA_API,
                    params={
                        "action": "wbgetentities",
                        "ids": "|".join(batch),
                        "props": "labels|claims",
                        "languages": "en",
                        "format": "json",
                    },
                    headers={"User-Agent": "alpr-research-pipeline/1.0 "
                                           "(academic research)"},
                    timeout=60,
                )
            except requests.RequestException as exc:
                log.warning("Wikidata request error (%s); retrying", exc)
                time.sleep(2 ** attempt)
                continue

            if resp.status_code in (429, 500, 502, 503, 504):
                wait = float(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
                log.warning("Wikidata %d; backing off %.0fs", resp.status_code, wait)
                time.sleep(min(wait, 60))
                continue

            if not resp.ok:
                log.warning("Wikidata HTTP %d", resp.status_code)
                time.sleep(2 ** attempt)
                continue

            payload = resp.json()
            err = payload.get("error")
            if err:
                if err.get("code") == "no-such-entity":
                    return None, True
                log.warning("Wikidata API error: %s", err.get("code"))
                time.sleep(2 ** attempt)
                continue

            return payload, False

        log.warning("Wikidata batch exhausted retries; leaving unresolved")
        return None, False

    def _resolve_recursive(self, batch: list[str]) -> dict[str, str]:
        """Resolve a batch, bisecting around ids the API says do not exist."""
        payload, permanent = self._request(batch)

        if payload is not None:
            return self._extract(payload)

        if not permanent:
            return {}  # transient: leave for a future run, cache nothing

        if len(batch) == 1:
            log.warning("Wikidata has no entity %s — malformed OSM tag", batch[0])
            self._rejected[batch[0]] = "no-such-entity"
            return {}

        mid = len(batch) // 2
        merged = self._resolve_recursive(batch[:mid])
        merged.update(self._resolve_recursive(batch[mid:]))
        return merged

    def _extract(self, payload: dict) -> dict[str, str]:
        """Pull English labels, rejecting entities that cannot be a vendor."""
        out: dict[str, str] = {}
        for qid, entity in (payload.get("entities") or {}).items():
            label = (entity.get("labels", {}).get("en", {}) or {}).get("value")
            if not label:
                continue

            instance_of = {
                snak.get("mainsnak", {}).get("datavalue", {})
                    .get("value", {}).get("id")
                for snak in entity.get("claims", {}).get("P31", [])
            }
            bad = instance_of & REJECT_INSTANCE_OF
            if bad:
                log.warning(
                    "Rejecting %s (%r): instance of %s — a mistyped OSM Q-ID, "
                    "not a vendor", qid, label, ", ".join(sorted(bad))
                )
                self._rejected[qid] = f"instance-of:{','.join(sorted(bad))}"
                continue

            out[qid] = label
        return out

    def resolve(self, qids: set[str]) -> dict[str, str]:
        """Return {qid: english_label} for every usable Q-ID."""
        wanted = {q for q in qids if valid_qid(q)}
        missing = sorted(wanted - self._cache.keys() - self._rejected.keys())

        if missing:
            log.info("Resolving %d new Wikidata Q-IDs...", len(missing))
            for i in range(0, len(missing), BATCH_SIZE):
                self._cache.update(
                    self._resolve_recursive(missing[i:i + BATCH_SIZE])
                )
            self._save()

        if self._rejected:
            log.info("%d Q-ID(s) rejected as unusable (see %s)",
                     len(self._rejected), self.rejected_path.name)

        return {q: self._cache[q] for q in wanted if q in self._cache}


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        log.warning("Could not read %s; starting fresh", path.name)
        return default
