"""Cached, backoff-retrying HTTP fetch shared by every extractor.

Raw responses are written to the cache before any parsing happens, so a parser
bug never costs another round trip to an upstream API.
"""
import hashlib
import time

import requests

from . import config

RETRY_STATUS = {429, 500, 502, 503, 504}
UA = "flock-alpr-research/0.1 (academic research; +https://github.com/)"


class CacheMiss(Exception):
    """Raised when offline fetch is requested and no cache entry exists."""


def cache_key(method: str, url: str, data, params) -> str:
    if isinstance(data, bytes):
        body = data
    elif isinstance(data, dict):
        body = repr(sorted(data.items())).encode()
    else:
        body = (data or "").encode()
    raw = f"{method}|{url}|".encode() + body
    raw += repr(sorted((params or {}).items())).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _request(method, url, data, params, timeout):
    return requests.request(
        method, url, data=data, params=params, timeout=timeout,
        headers={"User-Agent": UA},
    )


def fetch(url, *, method="GET", data=None, params=None, force=False,
          timeout=180, max_retries=5, offline=False) -> bytes:
    path = config.CACHE / f"{cache_key(method, url, data, params)}.bin"
    if path.exists() and not force:
        return path.read_bytes()
    if offline:
        raise CacheMiss(f"no cached response for {url}")

    delay = 5.0
    last = None
    for _ in range(max_retries):
        resp = _request(method, url, data, params, timeout)
        if resp.status_code == 200:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
            return resp.content
        last = resp.status_code
        if resp.status_code not in RETRY_STATUS:
            break
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(f"fetch failed for {url}: HTTP {last}")
