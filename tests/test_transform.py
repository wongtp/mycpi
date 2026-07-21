"""Unit tests for the TRANSFORM stage — pure functions, no DB or network."""
from transform import transform_product_data, getTotalPrice


def test_transform_maps_price_fields():
    raw = [{
        "upc": "0001",
        "price_info": {"regular": 4.99, "regularPerUnitEstimate": 0.25, "promo": 3.49},
    }]
    (row,) = transform_product_data(raw)
    assert row == {
        "upc": "0001",
        "regular_price": 4.99,
        "unit_price": 0.25,
        "sale_price": 3.49,
        "error": None,
    }


def test_transform_missing_promo_is_none():
    raw = [{"upc": "0002", "price_info": {"regular": 2.00, "regularPerUnitEstimate": 0.10}}]
    (row,) = transform_product_data(raw)
    assert row["sale_price"] is None
    assert row["error"] is None


def test_transform_none_price_info_flags_error_and_zeroes():
    raw = [{"upc": "0003", "price_info": None}]
    (row,) = transform_product_data(raw)
    assert row["error"] == "No price information available."
    assert row["regular_price"] == 0.0
    assert row["sale_price"] == 0.0


def test_total_prefers_sale_over_regular():
    products = [{"upc": "a", "regular_price": 5.00, "sale_price": 3.00, "error": None}]
    assert getTotalPrice(products) == 3.00


def test_total_uses_regular_when_no_sale():
    products = [{"upc": "a", "regular_price": 5.00, "sale_price": None, "error": None}]
    assert getTotalPrice(products) == 5.00


def test_total_skips_errored_rows():
    products = [
        {"upc": "a", "regular_price": 5.00, "sale_price": None, "error": None},
        {"upc": "b", "regular_price": 9.99, "sale_price": None, "error": "bad"},
    ]
    assert getTotalPrice(products) == 5.00


def test_total_ignores_nonpositive_prices():
    products = [{"upc": "a", "regular_price": 0.0, "sale_price": 0.0, "error": None}]
    assert getTotalPrice(products) == 0.0
