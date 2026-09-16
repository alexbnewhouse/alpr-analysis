import hashlib

from flock_alpr import config, http


def test_fetch_uses_cache_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE", tmp_path)
    url = "https://example.invalid/data"
    key = http.cache_key("GET", url, None, None)
    (tmp_path / f"{key}.bin").write_bytes(b"cached-payload")

    def explode(*a, **k):
        raise AssertionError("network must not be touched on cache hit")

    monkeypatch.setattr(http, "_request", explode)
    assert http.fetch(url) == b"cached-payload"


def test_cache_key_distinguishes_post_body():
    a = http.cache_key("POST", "https://x/y", b"query-A", None)
    b = http.cache_key("POST", "https://x/y", b"query-B", None)
    assert a != b


def test_cache_key_is_deterministic():
    assert http.cache_key("GET", "https://x", None, {"a": 1}) == \
        http.cache_key("GET", "https://x", None, {"a": 1})


def test_offline_fetch_raises_on_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE", tmp_path)
    try:
        http.fetch("https://example.invalid/never-cached", offline=True)
    except http.CacheMiss:
        return
    raise AssertionError("expected CacheMiss")


def test_cache_key_hashes_dict_body_stably():
    a = http.cache_key("POST", "https://x", {"b": 2, "a": 1}, None)
    b = http.cache_key("POST", "https://x", {"a": 1, "b": 2}, None)
    assert a == b
