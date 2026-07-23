from kroger_client import getToken, getProduct, getAllProductsForList
from bls_client import fetch_series, parse_series
from db import insert_watchlist, insert_snapshot_list, insert_basket_snapshot, refresh_summary, upsert_cpi
from transform import transform_product_data, getTotalPrice
from validate import validateProducts
import sys
import pathlib
from datetime import datetime

LOCATION_ID = "09700352"
PRODUCT_LIST_PATH = pathlib.Path(__file__).resolve().parent.parent / "productList.txt"

def main():
    try:
        token = getToken()
    except Exception as e:
        print(f"Error occurred while fetching token: {e}")
        return False

    with open(PRODUCT_LIST_PATH, "r") as f:
        upc_list = [line.strip() for line in f.readlines() if line.strip()]

    data = getAllProductsForList(upc_list, LOCATION_ID, token)

    for product in data:
        upc = product.get("upc")
        item_name = product.get("description")
        if item_name:
            insert_watchlist(upc, item_name)
        else:
            insert_watchlist(upc, "Unknown Product Name")

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
    priced = {p["upc"] for p in valid_products if not p.get("error")}
    missing = [upc for upc in upc_list if upc not in priced]

    if not missing:
        total_price = getTotalPrice(valid_products)
        insert_basket_snapshot(LOCATION_ID, total_price)
        return True

    print(f"Skipping basket snapshot: {len(missing)}/{expected} items missing "
          f"or flagged (UPCs: {', '.join(missing)}). Per-item snapshots still saved.")
    return False

def sync_cpi():
    # Fetch CPI data from BLS API
    series_id = "CUUR0000SAF11"  # Example series ID for All Items CPI
    try:
        end = datetime.now().year
        payload = fetch_series(series_id, end-1, end)
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