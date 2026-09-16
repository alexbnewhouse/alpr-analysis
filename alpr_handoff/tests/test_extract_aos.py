from pathlib import Path

import pytest

from flock_alpr import extract_aos

FIX = Path(__file__).parent / "fixtures" / "aos_sample.csv"


def test_parse_ori_strips_suffix_and_validates():
    assert extract_aos.parse_ori("FL0530000ALPR") == ("FL0530000", True)
    assert extract_aos.parse_ori("NC0920000DRON") == ("NC0920000", True)
    assert extract_aos.parse_ori("NOTANORI") == (None, False)
    assert extract_aos.parse_ori("") == (None, False)


def test_parse_filters_to_alpr_and_flags_flock():
    df = extract_aos.parse_aos(FIX.read_bytes())
    assert len(df) == 2  # the drone row is excluded
    assert df["is_flock"].sum() == 1


def test_invalid_ori_rows_are_retained_not_dropped():
    df = extract_aos.parse_aos(FIX.read_bytes())
    bad = df[~df["ori9_valid"]]
    assert len(bad) == 1
    assert bad.iloc[0]["ori9"] is None
    assert bad.iloc[0]["agency"] == "Raleigh PD"


def test_earliest_source_date_picks_minimum_across_link_columns():
    df = extract_aos.parse_aos(FIX.read_bytes())
    row = df[df["is_flock"]].iloc[0]
    assert str(row["earliest_source_date"]).startswith("2023-05-01")


def test_summary_as_of_date_extracted():
    df = extract_aos.parse_aos(FIX.read_bytes())
    assert df[df["is_flock"]].iloc[0]["summary_as_of_date"] == "July 2024"


def test_source_urls_joined():
    df = extract_aos.parse_aos(FIX.read_bytes())
    assert df[df["is_flock"]].iloc[0]["source_urls"] == "http://a|http://b"


def test_schema_drift_raises():
    with pytest.raises(ValueError, match="unexpected schema"):
        extract_aos.parse_aos(b"WrongCol,Other\n1,2\n")


def test_output_columns_are_stable():
    df = extract_aos.parse_aos(FIX.read_bytes())
    assert list(df.columns) == extract_aos.OUT_COLS
