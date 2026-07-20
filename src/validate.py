from db import get_last_price

def validateProducts(products):
    """
    Validate a list of products to ensure they have the required fields.

    Args:
        products (list): A list of product dictionaries.

    Returns:
        list: A list of valid products.
    """
    valid_products = []
    for product in products:
        regPrice = product.get("regular_price")
        upc = product.get("upc")
        if regPrice is None or regPrice <= 0:
            print(f"Product with UPC {product.get('upc')} has no regular price. Skipping.")
            product["error"] = "No regular price available."
            regPrice = 0.0
        lastPrice = get_last_price(upc)
        if regPrice is not None and regPrice > 0 and lastPrice:
            if ((float(lastPrice[0][1]) / float(regPrice) > 3 or float(lastPrice[0][1]) / float(regPrice) < 0.33)):
                print(f"Product with UPC {upc} has a significantly different regular price from the last recorded price. Skipping.")
                product["error"] = "Significant price change from last recorded price."
        valid_products.append(product)
    return valid_products
