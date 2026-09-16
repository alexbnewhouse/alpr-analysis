from pathlib import Path

from flock_alpr import extract_osm_history as h

FIX = Path(__file__).parent / "fixtures"


def test_clamp_window_respects_bounds():
    assert h.clamp_window("2020-01-01", "2030-01-01",
                          "2023-01-01", "2026-06-19") == ("2023-01-01", "2026-06-19")
    assert h.clamp_window("2024-01-01", "2025-01-01",
                          "2023-01-01", "2026-06-19") == ("2024-01-01", "2025-01-01")


def test_parse_series_returns_named_column():
    df = h.parse_series((FIX / "ohsome_sample.json").read_bytes(), "discovery_count")
    assert list(df.columns) == ["timestamp", "discovery_count"]
    assert df["discovery_count"].tolist() == [0.0, 18.0, 46.0]


def test_parse_grouped_series_splits_by_region():
    df = h.parse_grouped_series(
        (FIX / "ohsome_grouped_sample.json").read_bytes(), "discovery_count"
    )
    assert list(df.columns) == ["region", "timestamp", "discovery_count"]
    assert len(df) == 4
    assert set(df["region"]) == {"37183", "37119"}
    got = df[df["region"] == "37183"]["discovery_count"].tolist()
    assert got == [10.0, 25.0]


def test_parse_grouped_series_accepts_contributions_intervals():
    df = h.parse_grouped_series(
        (FIX / "ohsome_contributions_sample.json").read_bytes(), "contributors"
    )
    assert len(df) == 2
    assert df["contributors"].tolist() == [0.0, 5.0]
    # keyed on interval start, so it aligns with the snapshot series
    assert str(df.iloc[0]["timestamp"]).startswith("2023-01-01")


def test_parse_grouped_series_rejects_point_without_any_timestamp():
    import pytest
    bad = b'{"groupByResult":[{"groupByObject":"1","result":[{"value":1.0}]}]}'
    with pytest.raises(ValueError, match="lacks a timestamp"):
        h.parse_grouped_series(bad, "discovery_count")


def test_denominator_series_are_configured():
    names = [name for name, _, _ in h.SERIES]
    assert names == ["discovery_count", "total_nodes", "contributors"]


def test_installed_count_is_never_used_as_a_column_name():
    """Guard the spec's naming rule.

    OSM history measures discovery, not installation. Prose may discuss the
    banned name (the module docstrings explain exactly why it is banned), so
    this checks for it appearing as a quoted identifier -- i.e. actually used
    as a column -- rather than anywhere in the file text.
    """
    import ast

    for path in Path("flock_alpr").rglob("*.py"):
        tree = ast.parse(path.read_text())
        # Identify docstring Constant nodes by identity, not by value:
        # ast.get_docstring() returns cleaned text that no longer matches raw source.
        docstring_ids = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstring_ids.add(id(first.value))

        code_literals = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and id(n) not in docstring_ids
        ]
        assert not any("installed_count" in s for s in code_literals), \
            f"{path} uses the banned column name installed_count"
        assert not any(
            isinstance(n, ast.Name) and n.id == "installed_count"
            for n in ast.walk(tree)
        ), f"{path} binds a variable named installed_count"


def test_mark_complete_quarters_flags_the_trailing_partial():
    import pandas as pd
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(
            ["2026-01-01", "2026-04-01"], utc=True
        ),
        "discovery_count": [1.0, 2.0],
    })
    out = h.mark_complete_quarters(df, "2026-06-19")
    # Jan quarter ends 2026-04-01 (<= bound); Apr quarter ends 2026-07-01 (>).
    assert out["quarter_complete"].tolist() == [True, False]


def test_mark_complete_quarters_all_true_well_inside_window():
    import pandas as pd
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-04-01"], utc=True),
        "discovery_count": [1.0, 2.0],
    })
    out = h.mark_complete_quarters(df, "2026-06-19")
    assert out["quarter_complete"].all()


def test_run_emits_the_full_output_schema(tmp_path, monkeypatch):
    """Integration guard: run() renames timestamp->quarter, and the
    partial-quarter marker must be computed before that rename."""
    import json
    import pandas as pd

    monkeypatch.setattr(h.config, "RAW", tmp_path)
    monkeypatch.setattr(h, "data_window", lambda: ("2023-01-01", "2026-06-19"))

    grouped = (FIX / "ohsome_grouped_sample.json").read_bytes()
    contrib = (FIX / "ohsome_contributions_sample.json").read_bytes()

    def fake_fetch(url, **kw):
        return contrib if "contributions" in url else grouped

    monkeypatch.setattr(h.http, "fetch", fake_fetch)
    out = h.run({"type": "FeatureCollection", "features": []}, pause=0)

    assert list(out.columns) == h.OUT_COLS
    assert "timestamp" not in out.columns
    assert out["quarter_complete"].dtype == bool
    assert (tmp_path / "osm_alpr_history.parquet").exists()
