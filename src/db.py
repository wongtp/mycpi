import psycopg
from dotenv import load_dotenv

load_dotenv()

def insert_watchlist(upc, product_name):
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO watchlist (upc, product_name) VALUES (%s, %s) ON CONFLICT (upc) DO UPDATE SET product_name = EXCLUDED.product_name",
                (upc, product_name)
            )
            if (cur.rowcount > 0):
                print("Watchlist entry inserted successfully.")
            else:
                print("Watchlist entry already exists.")

def insert_snapshot_list(products, location_id):
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            for product in products:
                upc = product.get("upc")
                regular_price = product.get("regular_price")
                unit_price = product.get("unit_price")
                sale_price = product.get("sale_price")
                error = product.get("error")

                if regular_price is not None:
                    cur.execute(
                        "INSERT INTO price_snapshots (upc, location_id, regular_price, unit_price, sale_price, error) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (upc, location_id, recorded_at) DO NOTHING",
                        (upc, location_id, regular_price, unit_price, sale_price, error)
                    )
                    if (cur.rowcount > 0):
                        print(f"Snapshot for UPC {upc} inserted successfully.")
                else:
                    print(f"No snapshot inserted for UPC {upc} due to missing price information.")

def get_price_history(upc):
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT recorded_at, regular_price, unit_price, sale_price FROM price_snapshots WHERE upc = %s ORDER BY recorded_at DESC",
                (upc,)
            )
            rows = cur.fetchall()
    return rows

def get_last_price(upc):
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT recorded_at, regular_price, unit_price, sale_price FROM price_snapshots WHERE upc = %s ORDER BY recorded_at DESC LIMIT 1",
                (upc,)
            )
            rows = cur.fetchall()
    return rows

def insert_basket_snapshot(location_id, total_price):
    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO basket_snapshots (location_id, total_price) VALUES (%s, %s) ON CONFLICT (location_id, recorded_at) DO NOTHING",
                (location_id, total_price)
            )
            if (cur.rowcount > 0):
                print("Basket snapshot inserted successfully.")