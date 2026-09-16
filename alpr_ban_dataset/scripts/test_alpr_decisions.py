"""Tests for the municipal ALPR decision register.

Network-free: TIGER lookup is stubbed, so nothing here touches the Census.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "external"))
import build_alpr_decisions as bad_mod  # noqa: E402


PLACES = pd.DataFrame({
    # Austin TX is unique; California has TWO Mountain Views, which must stay
    # unresolved rather than being assigned to whichever sorts first.
    "place_geoid": ["4805000", "0649670", "0649671", "0107000"],
    "name": ["Austin", "Mountain View", "Mountain View", "Birmingham"],
    "state": ["TX", "CA", "CA", "AL"],
})
PLACES["key"] = bad_mod._norm(PLACES["name"]) + "|" + PLACES["state"]


@pytest.fixture
def run_on(tmp_path, monkeypatch):
    def _run(rows):
        src = tmp_path / "alpr_decisions.csv"
        pd.DataFrame(rows).to_csv(src, index=False)
        monkeypatch.setattr(bad_mod, "SRC", src)
        monkeypatch.setattr(bad_mod, "OUT", tmp_path / "out.parquet")
        monkeypatch.setattr(bad_mod, "place_names", lambda: PLACES)
        bad_mod.run()
        return pd.read_parquet(tmp_path / "out.parquet")
    return _run


def test_blank_override_does_not_become_a_fake_geoid(run_on):
    """An empty place_geoid must not be zero-padded into "0000000".

    That string is seven characters long, so a naive length check accepts it
    as a manual override and every unmatched row silently resolves to a place
    that does not exist. This shipped once.
    """
    out = run_on([dict(city="Austin", state="TX", action="canceled")])
    assert out["place_geoid"].tolist() == ["4805000"]
    assert "0000000" not in set(out["place_geoid"])


def test_ambiguous_name_is_dropped_not_guessed(run_on):
    out = run_on([
        dict(city="Mountain View", state="CA", action="canceled"),
        dict(city="Austin", state="TX", action="adopted"),
    ])
    assert out["city"].tolist() == ["Austin"]


def test_manual_override_wins_and_keeps_leading_zero(run_on):
    """A hand-supplied GEOID is honoured, and 107000 must become 0107000."""
    out = run_on([dict(city="Mountain View", state="CA",
                       place_geoid="107000", action="canceled")])
    assert out["place_geoid"].tolist() == ["0107000"]


def test_geoids_are_seven_character_strings(run_on):
    out = run_on([dict(city="Birmingham", state="AL", action="ordinance_ban")])
    assert out["place_geoid"].map(type).eq(str).all()
    assert set(out["place_geoid"].str.len()) == {7}
    assert out["place_geoid"].iloc[0].startswith("0")


def test_controlled_vocabulary_is_reported(run_on, capsys):
    run_on([dict(city="Austin", state="TX", action="cancelled")])  # British spelling
    assert "unrecognised" in capsys.readouterr().out


def test_approvals_are_retained_not_only_refusals(run_on):
    """The register must hold the comparison cases, or nothing is estimable."""
    out = run_on([
        dict(city="Austin", state="TX", action="adopted"),
        dict(city="Birmingham", state="AL", action="considered_no_action"),
    ])
    assert set(out["action"]) == {"adopted", "considered_no_action"}
