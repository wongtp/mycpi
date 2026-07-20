import os, requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("KROGER_CLIENT_ID")
CLIENT_SECRET = os.getenv("KROGER_CLIENT_SECRET")

def getToken():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("KROGER_CLIENT_ID and KROGER_CLIENT_SECRET must be set in the environment variables.")

    tokenObject = requests.post("https://api.kroger.com/v1/connect/oauth2/token", data={"grant_type": "client_credentials", "scope": "product.compact"}, auth=(CLIENT_ID, CLIENT_SECRET), timeout=(5,30))

    tokenObject.raise_for_status()

    token = tokenObject.json()["access_token"]

    return token

def getProduct(upc, location_id, token):
    productObject = requests.get(f"https://api.kroger.com/v1/products/{upc}?filter.locationId={location_id}", headers={"Authorization": f"Bearer {token}"}, timeout=(5,30))
    error = None
    price_info = None
    productObject.raise_for_status()
    product = productObject.json()

    data = product.get("data", {})
    items = data.get("items", [])

    if not items:
        print("No items found for the given UPC and location.")
        error = "No items found for the given UPC and location."
    else:
        price_info = items[0].get("price")
        if price_info is None:
            print(f"No price at location {location_id} for UPC {upc}.")
            error = "No price found for the given UPC and location."

    return {
        "description": data.get("description"),
        "price_info": price_info,
        "upc": upc,
        "error": error                                                                                         
    }

def getAllProductsForList(upc_list, location_id, token):
    products = []
    for upc in upc_list:
        try:
            product_data = getProduct(upc, location_id, token)
            products.append(product_data)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching product data for UPC {upc}: {e}")
            products.append({
                "description": None,
                "price_info": None,
                "upc": upc,
                "error": f"Request failed: {e}",   # or the HTTP status
            })
    return products