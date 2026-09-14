"""Overpass API client with mirror fallback, retries, and polite rate limiting.

Mirror list mirrors the one DeFlock/FlockHopper uses (worker/src/lib/overpass.ts),
with the public overpass-api.de instance kept last as a courtesy: it is the most
heavily loaded of the three.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

# Ordered by preference. deflock.org runs a mirror specifically for this dataset.
DEFAULT_ENDPOINTS = (
    "https://overpass.deflock.org/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)

# Overpass mirrors reject or throttle requests without an identifying User-Agent
# that carries a contact channel. Override via OverpassClient(user_agent=...).
DEFAULT_USER_AGENT = (
    "alpr-research-pipeline/1.0 "
    "(academic research; https://github.com/FoggedLens/deflock for data provenance)"
)


class OverpassError(RuntimeError):
    """Every mirror failed for a query."""


@dataclass
class OverpassResult:
    data: dict
    endpoint: str


class OverpassClient:
    def __init__(
        self,
        endpoints: tuple[str, ...] = DEFAULT_ENDPOINTS,
        user_agent: str = DEFAULT_USER_AGENT,
        # DeFlock's mirror sits behind a proxy that 504s at ~60s of wall clock
        # regardless of the [timeout:N] in the query. Waiting 180s for it just
        # delays failing over to a mirror that would have answered.
        timeout: float = 90.0,
        min_interval: float = 1.0,
        max_retries: int = 3,
    ):
        self.endpoints = endpoints
        self.timeout = timeout
        # Floor on wall-clock spacing between requests, applied globally across
        # mirrors. Overpass is donated infrastructure; do not hammer it.
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._last_request = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    def query(self, ql: str, allow_empty: bool = True) -> OverpassResult:
        """Run an Overpass QL query, falling back across mirrors then retrying.

        `allow_empty=False` treats a zero-element response as a failure. Use it
        for queries that must return data (a national fetch); leave it True for
        per-tile fetches, where empty ocean tiles are a legitimate result.
        """
        errors: list[str] = []

        for attempt in range(self.max_retries):
            for endpoint in self.endpoints:
                self._throttle()
                try:
                    resp = self.session.post(
                        endpoint, data={"data": ql}, timeout=self.timeout
                    )
                    if resp.status_code in (429, 504):
                        raise requests.HTTPError(
                            f"HTTP {resp.status_code} (throttled/timeout)"
                        )
                    resp.raise_for_status()
                    data = resp.json()

                    if not allow_empty and not data.get("elements"):
                        raise ValueError("empty elements array")

                    return OverpassResult(data=data, endpoint=endpoint)
                except Exception as exc:  # noqa: BLE001 - any failure -> next mirror
                    msg = f"{endpoint}: {type(exc).__name__}: {exc}"
                    log.warning("Overpass attempt failed: %s", msg)
                    errors.append(msg)

            if attempt < self.max_retries - 1:
                # Exponential backoff with jitter, shared across the mirror set.
                delay = (2**attempt) * 5 + random.uniform(0, 3)
                log.info("All mirrors failed; backing off %.1fs", delay)
                time.sleep(delay)

        raise OverpassError(
            f"All Overpass endpoints failed after {self.max_retries} rounds: "
            + "; ".join(errors[-6:])
        )

    def count(self, selector_body: str) -> int:
        """Run an `out count;` probe and return the total element count."""
        ql = f"[out:json][timeout:180];({selector_body});out count;"
        result = self.query(ql, allow_empty=True)
        elements = result.data.get("elements") or []
        if not elements:
            return 0
        return int(elements[0].get("tags", {}).get("total", 0))
