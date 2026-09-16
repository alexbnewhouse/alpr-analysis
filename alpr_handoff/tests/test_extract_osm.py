from pathlib import Path

import pandas as pd

from flock_alpr import extract_osm

FIX = Path(__file__).parent / "fixtures" / "overpass_sample.json"


def test_query_targets_alpr_nodes_in_state():
    q = extract_osm.build_query("NC")
    assert "US-NC" in q
    assert '"surveillance:type"="ALPR"' in q
    assert "out tags center meta" in q


def test_parse_extracts_tags_and_meta():
    df = extract_osm.parse_overpass(FIX.read_bytes(), "NC")
    assert len(df) == 2
    row = df.set_index("osm_id").loc[1001]
    assert row["manufacturer"] == "Flock Safety"
    assert row["operator_type"] == "police department"
    assert row["state"] == "NC"
    assert row["osm_version"] == 3
    assert str(row["osm_timestamp"]).startswith("2025-03-14")
    assert row["lat"] == 35.77


def test_parse_keeps_untagged_manufacturer_as_null():
    df = extract_osm.parse_overpass(FIX.read_bytes(), "NC")
    assert pd.isna(df.set_index("osm_id").loc[1002, "manufacturer"])


def test_parse_returns_stable_column_set():
    df = extract_osm.parse_overpass(FIX.read_bytes(), "NC")
    assert list(df.columns) == extract_osm.COLUMNS


def test_parse_handles_empty_result():
    df = extract_osm.parse_overpass(b'{"elements": []}', "WY")
    assert len(df) == 0
    assert list(df.columns) == extract_osm.COLUMNS


def test_run_continues_past_a_failed_state(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(extract_osm, "STATE_DIR", tmp_path)

    def flaky(state, force=False):
        if state == "KS":
            raise RuntimeError("HTTP 504")
        return extract_osm.parse_overpass(FIX.read_bytes(), state)

    monkeypatch.setattr(extract_osm, "fetch_state", flaky)
    monkeypatch.setattr(extract_osm.config, "RAW", tmp_path)
    out = extract_osm.run(states=["NC", "KS", "SC"], pause=0)

    # The two good states survive rather than being discarded with the bad one.
    assert set(out["state"]) == {"NC", "SC"}
    assert "FAILED states (1): KS" in capsys.readouterr().out


def test_run_raises_only_when_every_state_fails(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(extract_osm, "STATE_DIR", tmp_path)

    def always_fail(state, force=False):
        raise RuntimeError("HTTP 504")

    monkeypatch.setattr(extract_osm, "fetch_state", always_fail)
    with pytest.raises(RuntimeError, match="no states extracted"):
        extract_osm.run(states=["NC", "KS"], pause=0)


def test_vendor_coalesces_brand_when_manufacturer_absent():
    """744 California nodes tag brand=Flock Safety with no manufacturer."""
    payload = (b'{"elements":[{"type":"node","id":1,"lat":32.6,"lon":-117.0,'
               b'"version":1,"timestamp":"2025-01-01T00:00:00Z","tags":'
               b'{"surveillance:type":"ALPR","brand":"Flock Safety",'
               b'"operator":"Chula Vista Police Department"}}]}')
    df = extract_osm.parse_overpass(payload, "CA")
    assert df.iloc[0]["vendor"] == "Flock Safety"
    assert extract_osm.is_flock(df["vendor"]).all()


def test_vendor_prefers_manufacturer_over_brand():
    payload = (b'{"elements":[{"type":"node","id":1,"lat":1,"lon":1,"version":1,'
               b'"timestamp":"2025-01-01T00:00:00Z","tags":'
               b'{"surveillance:type":"ALPR","manufacturer":"Motorola Solutions",'
               b'"brand":"AutoVu Cloudrunner"}}]}')
    df = extract_osm.parse_overpass(payload, "CA")
    assert df.iloc[0]["vendor"] == "Motorola Solutions"


def test_vendor_falls_back_to_surveillance_prefixed_tags():
    payload = (b'{"elements":[{"type":"node","id":1,"lat":1,"lon":1,"version":1,'
               b'"timestamp":"2025-01-01T00:00:00Z","tags":'
               b'{"surveillance:type":"ALPR","surveillance:brand":"Genetec"}}]}')
    df = extract_osm.parse_overpass(payload, "CA")
    assert df.iloc[0]["vendor"] == "Genetec"


def test_vendor_is_null_when_no_vendor_tag_present():
    df = extract_osm.parse_overpass(FIX.read_bytes(), "NC")
    assert df.set_index("osm_id").loc[1002, "vendor"] is None


def test_is_flock_is_case_insensitive_and_null_safe():
    import pandas as pd
    s = pd.Series(["Flock Safety", "flock safety", "Axis Communications", None])
    assert extract_osm.is_flock(s).tolist() == [True, True, False, False]


def test_parse_records_no_endpoint_until_fetch(tmp_path):
    """source_endpoint is stamped by fetch_state, not by the parser."""
    df = extract_osm.parse_overpass(FIX.read_bytes(), "NC")
    assert "source_endpoint" not in df.columns


def test_mirror_sourced_checkpoint_is_retried(tmp_path, monkeypatch):
    """Mirrors lag the primary; their checkpoints must not be trusted."""
    monkeypatch.setattr(extract_osm, "STATE_DIR", tmp_path)
    df = extract_osm.parse_overpass(FIX.read_bytes(), "PA")
    df["source_endpoint"] = "https://overpass.kumi.systems/api/interpreter"
    df.to_parquet(tmp_path / "PA.parquet", index=False)

    calls = []

    def fake_fetch(url, **kw):
        calls.append(url)
        return FIX.read_bytes()

    monkeypatch.setattr(extract_osm.http, "fetch", fake_fetch)
    out = extract_osm.fetch_state("PA")
    assert calls, "a mirror-sourced checkpoint must be refetched"
    assert calls[0] == extract_osm.config.OVERPASS_MIRRORS[0]
    assert out["source_endpoint"].iloc[0] == extract_osm.config.OVERPASS_MIRRORS[0]


def test_primary_sourced_checkpoint_is_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_osm, "STATE_DIR", tmp_path)
    df = extract_osm.parse_overpass(FIX.read_bytes(), "NC")
    df["source_endpoint"] = extract_osm.config.OVERPASS_MIRRORS[0]
    df.to_parquet(tmp_path / "NC.parquet", index=False)

    def explode(*a, **k):
        raise AssertionError("primary-sourced checkpoint must be reused")

    monkeypatch.setattr(extract_osm.http, "fetch", explode)
    assert len(extract_osm.fetch_state("NC")) == 2


def test_legacy_checkpoint_without_endpoint_is_treated_as_suspect(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_osm, "STATE_DIR", tmp_path)
    extract_osm.parse_overpass(FIX.read_bytes(), "NC").to_parquet(
        tmp_path / "NC.parquet", index=False
    )
    calls = []
    monkeypatch.setattr(extract_osm.http, "fetch",
                        lambda url, **kw: (calls.append(url), FIX.read_bytes())[1])
    extract_osm.fetch_state("NC")
    assert calls, "checkpoints predating endpoint tracking must be refetched"
