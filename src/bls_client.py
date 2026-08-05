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
    request = {
        "seriesid": [series_id],
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    # An unregistered v2 request is capped at a much smaller quota; send the key
    # only when there is one, since an empty string is rejected outright.
    if BLS_API_KEY:
        request["registrationKey"] = BLS_API_KEY

    response = session.post(BLS_URL, json=request, timeout=(5,30))
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "REQUEST_SUCCEEDED":
        # BLS returns `message` as a list of strings.
        messages = payload.get("message") or ["Unknown error"]
        if isinstance(messages, str):
            messages = [messages]
        raise RuntimeError(f"BLS API request failed: {'; '.join(messages)}")
    return payload

def parse_series(payload):
    rows = []
    for series in (payload.get("Results") or {}).get("series") or []:
        sid = series.get("seriesID")
        for d in series.get("data") or []:
            period = d.get("period", "")
            # Monthly periods only: M13 is the annual average, and semiannual
            # series use S01/S02.
            if not period.startswith("M") or period == "M13":
                continue
            try:
                value = float(d["value"].replace(",", ""))
            except (ValueError, AttributeError, KeyError):
                continue  # BLS uses "-" (or blanks) for missing/suppressed data
            rows.append({
                "series_id": sid,
                "year": int(d["year"]),
                "month": int(period[1:]),   # "M04" -> 4
                "value": value,
            })
    return rows
