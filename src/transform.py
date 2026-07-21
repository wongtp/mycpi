def transform_product_data(product):
    result = []
    for item in product:
        error = None
        upc = item.get("upc")
        price_info = item.get("price_info", {})
        if price_info is None:  
            print(f"No price information available for UPC {upc}. Skipping.")
            error = "No price information available."
            regular_price = 0.0
            unit_price = 0.0
            sale_price = 0.0
        else:
            regular_price = price_info.get("regular")
            unit_price = price_info.get("regularPerUnitEstimate")
            sale_price = price_info.get("promo")

        result.append({
            "upc": upc,
            "regular_price": regular_price,
            "unit_price": unit_price,
            "sale_price": sale_price,
            "error": error
        })
    return result

def getTotalPrice(product):
    total_price = 0.0
    for item in product:
        if item.get("error") is not None:
            continue
        regular_price = item.get("regular_price")
        sale_price = item.get("sale_price")
        if sale_price is not None and sale_price > 0:
            total_price += sale_price
        elif regular_price is not None and regular_price > 0:
            total_price += regular_price
    return total_price