"""Unit tests for the VALIDATE stage.

`validate.get_last_prices` hits Postgres, so each test monkeypatches it to
return a canned {upc: last clean regular price} map (empty for the first run).
"""
import validate


def _last(**prices):
    """Stand in for the batched last-clean-price lookup."""
    return lambda upcs: dict(prices)


def test_missing_price_is_flagged(monkeypatch):
    monkeypatch.setattr(validate, "get_last_prices", _last())
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": None}])
    assert row["error"] == "No regular price available."


def test_nonpositive_price_is_flagged(monkeypatch):
    monkeypatch.setattr(validate, "get_last_prices", _last())
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 0}])
    assert row["error"] == "No regular price available."


def test_first_run_no_history_passes(monkeypatch):
    monkeypatch.setattr(validate, "get_last_prices", _last())
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 4.99}])
    assert row.get("error") is None


def test_price_within_bounds_passes(monkeypatch):
    monkeypatch.setattr(validate, "get_last_prices", _last(a=5.00))
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 5.50}])
    assert row.get("error") is None


def test_price_crash_is_flagged(monkeypatch):
    # last 5.00 vs new 0.01 -> ratio 500, well past the 3x guard
    monkeypatch.setattr(validate, "get_last_prices", _last(a=5.00))
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 0.01}])
    assert row["error"] == "Significant price change from last recorded price."


def test_price_spike_is_flagged(monkeypatch):
    # last 5.00 vs new 100.00 -> ratio 0.05, past the 0.33 lower guard
    monkeypatch.setattr(validate, "get_last_prices", _last(a=5.00))
    (row,) = validate.validateProducts([{"upc": "a", "regular_price": 100.00}])
    assert row["error"] == "Significant price change from last recorded price."


def test_existing_error_is_not_overwritten(monkeypatch):
    # The extract stage knows *why* the fetch failed; validate's generic message
    # must not replace it.
    monkeypatch.setattr(validate, "get_last_prices", _last())
    (row,) = validate.validateProducts(
        [{"upc": "a", "regular_price": None, "error": "Request failed (HTTP 404): boom"}]
    )
    assert row["error"] == "Request failed (HTTP 404): boom"


def test_batched_lookup_is_called_once_for_the_whole_basket(monkeypatch):
    calls = []

    def fake(upcs):
        calls.append(list(upcs))
        return {}

    monkeypatch.setattr(validate, "get_last_prices", fake)
    validate.validateProducts([
        {"upc": "a", "regular_price": 1.00},
        {"upc": "b", "regular_price": 2.00},
    ])
    assert calls == [["a", "b"]]


def test_all_rows_are_returned_not_dropped(monkeypatch):
    monkeypatch.setattr(validate, "get_last_prices", _last())
    rows = validate.validateProducts([
        {"upc": "a", "regular_price": 1.00},
        {"upc": "b", "regular_price": None},
    ])
    assert [r["upc"] for r in rows] == ["a", "b"]
