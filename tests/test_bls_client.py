"""Unit tests for BLS response parsing — pure function, no network."""
import pytest

from bls_client import parse_series


def _payload(*data):
    return {"Results": {"series": [{"seriesID": "CUUR0000SAF11", "data": list(data)}]}}


def test_parses_monthly_rows():
    rows = parse_series(_payload({"year": "2026", "period": "M04", "value": "312.456"}))
    assert rows == [{
        "series_id": "CUUR0000SAF11",
        "year": 2026,
        "month": 4,
        "value": 312.456,
    }]


def test_strips_thousands_separator():
    (row,) = parse_series(_payload({"year": "2026", "period": "M04", "value": "1,312.4"}))
    assert row["value"] == 1312.4


def test_skips_annual_average():
    # M13 is the annual average, not a 13th month.
    assert parse_series(_payload({"year": "2026", "period": "M13", "value": "300"})) == []


def test_skips_semiannual_periods():
    # Some series publish S01/S02; int("01") would otherwise pass silently.
    assert parse_series(_payload({"year": "2026", "period": "S01", "value": "300"})) == []


def test_skips_suppressed_values():
    assert parse_series(_payload({"year": "2026", "period": "M04", "value": "-"})) == []


@pytest.mark.parametrize("payload", [{}, {"Results": {}}, {"Results": {"series": None}}])
def test_missing_sections_return_empty(payload):
    # A degenerate response should yield nothing, not raise inside the cron run.
    assert parse_series(payload) == []
