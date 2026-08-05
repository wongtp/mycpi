from kroger_client import getToken, getAllProductsForList
from bls_client import fetch_series, parse_series
from db import insert_watchlist, insert_snapshot_list, insert_basket_snapshot, refresh_summary, upsert_cpi
from transform import transform_product_data, getTotalPrice
from validate import validateProducts
from config import LOCATION_ID, PRODUCT_LIST_PATH, CPI_SERIES
import sys
from datetime import datetime

def load_upc_list():
    """Watchlist UPCs, de-duplicated but kept in file order.

    The basket total sums one entry per line, so a UPC listed twice would both
    double-count that item and inflate the expected-item count the
    completeness check compares against.
    """
    try:
        text = PRODUCT_LIST_PATH.read_text()
    except OSError as e:
        print(f"Could not read the product list at {PRODUCT_LIST_PATH}: {e}")
        return []

    seen = {}
    for line in text.splitlines():
        upc = line.strip()
        if upc:
            seen[upc] = None
    return list(seen)

def main():
    upc_list = load_upc_list()
    if not upc_list:
        print("No UPCs to price — check productList.txt.")
        return False

    try:
        token = getToken()
    except Exception as e:
        print(f"Error occurred while fetching token: {e}")
        return False

    data = getAllProductsForList(upc_list, LOCATION_ID, token)

    for product in data:
        # A failed fetch has no description; passing it through as None lets the
        # upsert keep whatever name a previous successful run recorded.
        insert_watchlist(product.get("upc"), product.get("description"))

    #fetch bls data
    sync_cpi()

    cleaned_data = transform_product_data(data)
    valid_products = validateProducts(cleaned_data)

    #run report
    errcount = 0
    for product in valid_products:
        upc = product.get("upc")
        regular_price = product.get("regular_price")
        unit_price = product.get("unit_price")
        sale_price = product.get("sale_price")
        error = product.get("error")
        if error:
            errcount += 1
        print(f"UPC: {upc}, Regular Price: {regular_price}, Unit Price: {unit_price}, Sale Price: {sale_price}, Error: {error}")

    print(f"Total errors: {errcount}")

    # Per-item history is always worth keeping (flag-don't-drop).
    insert_snapshot_list(valid_products, LOCATION_ID)

    #refresh materialized summary view for basket snapshot
    refresh_summary()

    # A basket index entry is only comparable if it sums the SAME full set of
    # items every run. Only write one when every watchlist item priced cleanly;
    # otherwise skip it (a partial sum would look like deflation) and fail the run.
    expected = len(upc_list)
    priced = {p.get("upc") for p in valid_products if not p.get("error")}
    missing = [upc for upc in upc_list if upc not in priced]

    if not missing:
        total_price = getTotalPrice(valid_products)
        insert_basket_snapshot(LOCATION_ID, total_price)
        return True

    print(f"Skipping basket snapshot: {len(missing)}/{expected} items missing "
          f"or flagged (UPCs: {', '.join(missing)}). Per-item snapshots still saved.")
    return False

def sync_cpi():
    """Refresh the national CPI reference series.

    Fetches three calendar years, not two: BLS publishes a month or two in
    arrears, so early in a new year a two-year window can end before the
    prior-year month the dashboard's YoY figure needs.
    """
    try:
        end = datetime.now().year
        payload = fetch_series(CPI_SERIES, end - 2, end)
        rows = parse_series(payload)
        upsert_cpi(rows)
        print("CPI data synchronized successfully.")
    except Exception as e:
        print(f"Error occurred while synchronizing CPI data: {e}")

if __name__ == "__main__":
    try:
        success = main()
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
    sys.exit(0 if success else 1)
