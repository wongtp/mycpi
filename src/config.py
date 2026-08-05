"""Settings shared by the pipeline (`main.py`) and the dashboard (`app.py`).

Both entry points need the CPI series id; keeping one copy stops the ETL from
loading one series while the UI reads and labels another.
"""
import pathlib

# One fixed store — the basket is only comparable over time at a single location.
LOCATION_ID = "09700352"

PRODUCT_LIST_PATH = pathlib.Path(__file__).resolve().parent.parent / "productList.txt"

# BLS "food at home", US city average — the closest national analogue to a
# grocery basket. Monthly, and published with a lag of a month or two.
CPI_SERIES = "CUUR0000SAF11"
CPI_SERIES_LABEL = "US food-at-home CPI"
