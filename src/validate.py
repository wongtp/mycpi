from db import get_last_prices

# A price this far from the last clean snapshot is far more likely to be a bad
# read than a real move, so the row is flagged rather than trusted.
MAX_PRICE_RATIO = 3.0


def _flag(product, message):
    """Record a validation failure without discarding an earlier, more specific one."""
    if not product.get("error"):
        product["error"] = message


def validateProducts(products):
    """
    Validate a list of products to ensure they have the required fields.

    Args:
        products (list): A list of product dictionaries.

    Returns:
        list: The same products, with `error` set on any that fail a check.
              Rows are flagged, never dropped — per-item history is still worth
              keeping, and the caller decides what a flag means for the basket.
    """
    last_prices = get_last_prices([product.get("upc") for product in products])

    valid_products = []
    for product in products:
        upc = product.get("upc")
        regPrice = product.get("regular_price")

        if regPrice is None or regPrice <= 0:
            print(f"Product with UPC {upc} has no regular price. Skipping.")
            _flag(product, "No regular price available.")
            valid_products.append(product)
            continue

        lastPrice = last_prices.get(upc)
        if lastPrice:
            ratio = float(lastPrice) / float(regPrice)
            if ratio > MAX_PRICE_RATIO or ratio < 1 / MAX_PRICE_RATIO:
                print(f"Product with UPC {upc} has a significantly different regular price from the last recorded price. Skipping.")
                _flag(product, "Significant price change from last recorded price.")

        valid_products.append(product)
    return valid_products
