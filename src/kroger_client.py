import os, requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

CLIENT_ID = os.getenv("KROGER_CLIENT_ID")
CLIENT_SECRET = os.getenv("KROGER_CLIENT_SECRET")

def _session():
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
    )
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    return s

def getToken(session=None):
    if not CLIENT_ID or not CLIENT_SECRET:
        raise ValueError("KROGER_CLIENT_ID and KROGER_CLIENT_SECRET must be set in the environment variables.")

    session = session or _session()

    tokenObject = session.post("https://api.kroger.com/v1/connect/oauth2/token", data={"grant_type": "client_credentials", "scope": "product.compact"}, auth=(CLIENT_ID, CLIENT_SECRET), timeout=(5,30))

    tokenObject.raise_for_status()

    token = tokenObject.json().get("access_token")
    if not token:
        raise RuntimeError("Kroger token response contained no access_token.")

    return token

def getProduct(upc, location_id, token, session=None):
    session = session or _session()
    productObject = session.get(f"https://api.kroger.com/v1/products/{upc}?filter.locationId={location_id}", headers={"Authorization": f"Bearer {token}"}, timeout=(5,30))
    error = None
    price_info = None
    productObject.raise_for_status()
    product = productObject.json()

    # A malformed or empty response should read as "no price", not crash the run
    # for the other items in the basket.
    data = product.get("data") or {}
    items = data.get("items") or []

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
    session = _session()
    products = []
    for upc in upc_list:
        try:
            product_data = getProduct(upc, location_id, token, session=session)
            products.append(product_data)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching product data for UPC {upc}: {e}")
            # Keep the status code: a 401 (token) and a 404 (delisted item) call
            # for very different fixes, and the log is the only record.
            status = getattr(e.response, "status_code", None)
            detail = f"HTTP {status}" if status else type(e).__name__
            products.append({
                "description": None,
                "price_info": None,
                "upc": upc,
                "error": f"Request failed ({detail}): {e}",
            })
    return products
