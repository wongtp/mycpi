import pandas as pd


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

def yoy(frame, value_col):
    """Latest value in a (day, value) frame and its % change vs. 12 months prior.

    Matches the prior-year row by date, not by position, so a gap in the series
    can't silently turn into a 12-row offset. Returns (latest, pct); pct is None
    when the prior-year month is missing, null, or zero.
    """
    if frame.empty:
        return None, None

    frame = frame.sort_values("day")
    days = pd.to_datetime(frame["day"])
    latest = frame[value_col].iloc[-1]

    prior_row = frame[days == days.iloc[-1] - pd.DateOffset(years=1)]
    if prior_row.empty:
        return latest, None

    prior = prior_row[value_col].iloc[-1]
    if pd.isna(prior) or prior == 0:
        return latest, None

    return latest, (latest - prior) / prior * 100


def to_index(frame, value_col, base_date):
    """Rebase a (day, value) frame to 100 at the last value on/before base_date.

    If no row falls on/before base_date, the first row is used as the base
    instead — so a series that starts after base_date is rebased to its own
    opening value rather than returning empty.
    """
    frame = frame.sort_values("day").copy()
    # `day` may arrive as datetime.date (psycopg) or datetime64 (pandas); coerce
    # both sides so the comparison doesn't depend on what the caller passes in.
    days = pd.to_datetime(frame["day"])
    on_or_before = frame[days <= pd.to_datetime(base_date)]

    if on_or_before.empty:
        base = frame[value_col].iloc[0]
    else:
        base = on_or_before[value_col].iloc[-1]

    frame["index"] = frame[value_col] / base * 100
    return frame
