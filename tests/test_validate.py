"""Unit tests for the VALIDATE stage.

`validate.get_last_price` hits Postgres, so each test monkeypatches it to
return a canned "previous snapshot" (or None for the first-run case).
"""
import validate


def _last_price(regular):
    """Shape get_last_price returns: [(recorded_at, regular, unit, sale)]."""
    return [(None, regular, None, None)]


def test_missing_price_is_flagged(monkeypatch):
    monkeypatch.setattr(validate, "get_last_price", lambda upc: None)
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": None}])
    assert row["error"] == "No regular price available."


def test_nonpositive_price_is_flagged(monkeypatch):
    monkeypatch.setattr(validate, "get_last_price", lambda upc: None)
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 0}])
    assert row["error"] == "No regular price available."


def test_first_run_no_history_passes(monkeypatch):
    monkeypatch.setattr(validate, "get_last_price", lambda upc: None)
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 4.99}])
    assert row.get("error") is None


def test_price_within_bounds_passes(monkeypatch):
    monkeypatch.setattr(validate, "get_last_price", lambda upc: _last_price(5.00))
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 5.50}])
    assert row.get("error") is None


def test_price_spike_is_flagged(monkeypatch):
    # last 5.00 vs new 0.01 -> ratio 500, well past the 3x guard
    monkeypatch.setattr(validate, "get_last_price", lambda upc: _last_price(5.00))
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 0.01}])
    assert row["error"] == "Significant price change from last recorded price."


def test_price_crash_is_flagged(monkeypatch):
    # last 5.00 vs new 100.00 -> ratio 0.05, past the 0.33 lower guard
    monkeypatch.setattr(validate, "get_last_price", lambda upc: _last_price(5.00))
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 100.00}])
    assert row["error"] == "Significant price change from last recorded price."
