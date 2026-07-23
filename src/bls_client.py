import os, requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
BLS_API_KEY = os.getenv("BLS_API_KEY")
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

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

def fetch_series(series_id, start_year, end_year, session=None):
    session = session or _session()
    payload = {
        "seriesid": [series_id],
        "startyear": str(start_year),
        "endyear": str(end_year),
        "registrationKey": BLS_API_KEY
    }
    response = session.post(BLS_URL, json=payload, timeout=(5,30))
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API request failed: {payload.get('message', 'Unknown error')}")
    return payload

def parse_series(payload):
    rows = []
    for series in payload["Results"]["series"]:
        sid = series["seriesID"]
        for d in series["data"]:
            if d["period"] == "M13":
                continue
            try:
                value = float(d["value"].replace(",", ""))
            except ValueError:
                continue  # BLS uses "-" (or blanks) for missing/suppressed data
            rows.append({
                "series_id": sid,
                "year": int(d["year"]),
                "month": int(d["period"][1:]),   # "M04" -> 4
                "value": value,
            })
    return rows
