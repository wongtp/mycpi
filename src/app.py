import streamlit as st
import pandas as pd
import psycopg
from dotenv import load_dotenv
import altair as alt

from transform import yoy

load_dotenv()

st.set_page_config(
    layout="wide",
    page_title="mycpi — personal price index",
    page_icon="🛒",
)

# --- palette (dataviz slots 1 & 2: blue / orange, light mode) ---
REGULAR = "#2a78d6"
SALE = "#eb6834"
LABELS = {"avg_regular": "regular", "best_sale": "sale"}
COLORS = {"regular": REGULAR, "sale": SALE}

# National CPI is context, not a peer series — neutral gray keeps it out of the
# categorical palette so it never reads as comparable to the basket lines.
NATIONAL = "#6b6a66"
AXIS = "#898781"

# BLS "food at home", US city average — the closest national analogue to a
# grocery basket. Monthly, and published with a lag of a month or two.
CPI_SERIES = "CUUR0000SAF11"
CPI_SERIES_LABEL = "US food-at-home CPI"


# ---------------------------------------------------------------- data
@st.cache_data(ttl=3600)
def load_basket():
    with psycopg.connect() as conn:
        cur = conn.execute(
            "SELECT date_trunc('day', recorded_at)::date AS day, "
            "round(avg(total_price), 2)::float8 AS basket_price "
            "FROM basket_snapshots GROUP BY 1 ORDER BY 1"
        )
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


@st.cache_data(ttl=3600)  # match the hourly cron; reruns won't re-query
def load_index():
    with psycopg.connect() as conn:
        cur = conn.execute(
            "SELECT upc, product_name, day, avg_regular, avg_unit, best_sale "
            "FROM daily_price_index ORDER BY day"
        )
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


@st.cache_data(ttl=3600)
def load_last_updated():
    with psycopg.connect() as conn:
        row = conn.execute("SELECT max(recorded_at) FROM basket_snapshots").fetchone()
        return row[0]

@st.cache_data(ttl=3600)
def load_cpi(series_id=CPI_SERIES):
    with psycopg.connect() as conn:
        cur = conn.execute(
            "SELECT make_date(year, month, 1) AS day, value::float8 AS value "
            "FROM bls_cpi WHERE series_id = %s ORDER BY 1",
            (series_id,),
        )
        cols = [c.name for c in cur.description]
        frame = pd.DataFrame(cur.fetchall(), columns=cols)
        frame["day"] = pd.to_datetime(frame["day"])
        return frame


# ---------------------------------------------------------------- charts
def basket_chart(basket):
    base = alt.Chart(basket).encode(
        x=alt.X("day:T", title=None, axis=alt.Axis(format="%b %d", tickCount=6)),
        y=alt.Y(
            "basket_price:Q",
            title="Basket total",
            scale=alt.Scale(zero=False),
            axis=alt.Axis(format="$,.0f"),
        ),
    )
    area = base.mark_area(
        line={"color": REGULAR, "strokeWidth": 2},
        color=alt.Gradient(
            gradient="linear",
            stops=[
                alt.GradientStop(color="#ffffff", offset=0),
                alt.GradientStop(color=REGULAR, offset=1),
            ],
            x1=1, x2=1, y1=1, y2=0,
        ),
        opacity=0.25,
    )
    points = base.mark_point(color=REGULAR, filled=True, size=55).encode(
        tooltip=[
            alt.Tooltip("day:T", title="Day", format="%b %d, %Y"),
            alt.Tooltip("basket_price:Q", title="Basket", format="$,.2f"),
        ]
    )
    return (area + points).properties(height=300)


def cpi_chart(cpi):
    """Standalone monthly BLS line — own axis, own scale, deliberately not
    plotted against the basket (different frequency, no overlapping dates)."""
    return (
        alt.Chart(cpi)
        .mark_line(color=NATIONAL, strokeWidth=2,
                   point=alt.OverlayMarkDef(filled=True, size=25, color=NATIONAL))
        .encode(
            x=alt.X("day:T", title=None,
                    axis=alt.Axis(format="%b '%y", tickCount=4, labelAngle=0,
                                  labelColor=AXIS, domainColor=AXIS, tickColor=AXIS)),
            y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False),
                    axis=alt.Axis(format=".0f", labelColor=AXIS, domainColor=AXIS,
                                  tickColor=AXIS, tickCount=3)),
            tooltip=[
                alt.Tooltip("day:T", title="Month", format="%b %Y"),
                alt.Tooltip("value:Q", title="Index", format=".1f"),
            ],
        )
        .properties(height=110)
    )


def mini_chart(series):
    long = series.melt(
        id_vars="day", value_vars=["avg_regular", "best_sale"],
        var_name="metric", value_name="price",
    )
    long["metric"] = long["metric"].map(LABELS)
    long = long.dropna(subset=["price"])
    return (
        alt.Chart(long)
        .mark_line(point=alt.OverlayMarkDef(filled=True, size=25))
        .encode(
            x=alt.X("day:T", title=None,
                    axis=alt.Axis(format="%b %d", tickCount=3, labelAngle=0)),
            y=alt.Y("price:Q", title=None, scale=alt.Scale(zero=False),
                    axis=alt.Axis(format="$,.0f")),
            color=alt.Color(
                "metric:N",
                scale=alt.Scale(domain=list(COLORS), range=list(COLORS.values())),
                legend=None,  # one shared legend above the grid instead
            ),
            tooltip=[
                alt.Tooltip("day:T", title="Day", format="%b %d"),
                alt.Tooltip("metric:N", title="Price"),
                alt.Tooltip("price:Q", format="$,.2f"),
            ],
        )
        .properties(height=140)
    )


def pct_change(series, col):
    """Latest vs. previous non-null value for a product's price column."""
    vals = series.dropna(subset=[col]).sort_values("day")[col]
    if len(vals) < 2 or vals.iloc[-2] == 0:
        return vals.iloc[-1] if len(vals) else None, None
    latest, prev = vals.iloc[-1], vals.iloc[-2]
    return latest, (latest - prev) / prev * 100


# ---------------------------------------------------------------- header
last_updated = load_last_updated()
stamp = last_updated.strftime("%b %d, %Y · %-I%p") if last_updated else "no data yet"

st.title("🛒 mycpi")
st.caption(
    "A personal consumer price index. The price of one fixed household basket, "
    "snapshotted from Kroger every hour, tracked over time — a price history that "
    "doesn't exist anywhere else."
)

basket = load_basket()
df = load_index()
cpi = load_cpi()

# ---------------------------------------------------------------- KPI row
if not basket.empty:
    current = basket["basket_price"].iloc[-1]
    first = basket["basket_price"].iloc[0]
    since_start = current - first
    prev = basket["basket_price"].iloc[-2] if len(basket) > 1 else None

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Basket now", f"${current:,.2f}",
        delta=(f"${current - prev:+,.2f} vs. prior day" if prev is not None else None),
        delta_color="inverse",  # rising prices are bad
    )
    k2.metric(
        "Since first snapshot", f"${since_start:+,.2f}",
        delta=(f"{since_start / first * 100:+.1f}%" if first else None),
        delta_color="inverse",
    )
    k3.metric("Items tracked", f"{df['product_name'].nunique()}")
    k4.metric("Days of history", f"{basket['day'].nunique()}")

    cpi_latest, cpi_yoy = yoy(cpi, "value")
    cpi_asof = cpi["day"].iloc[-1].strftime("%b %Y") if not cpi.empty else None
    k5.metric(
        CPI_SERIES_LABEL,
        f"{cpi_latest:,.1f}" if cpi_latest is not None else "—",
        delta=(f"{cpi_yoy:+.1f}% YoY" if cpi_yoy is not None else None),
        delta_color="inverse",
        help=(
            f"BLS series {CPI_SERIES} — food at home, US city average. A national "
            "reference point, not a like-for-like comparison to the basket: it is "
            "monthly, covers a different set of goods, and lags."
            + (f" Latest published: {cpi_asof}." if cpi_asof else " No data loaded yet.")
        ),
    )

st.caption(f"Last updated {stamp}")
st.divider()

# ---------------------------------------------------------------- basket
st.subheader("Whole-basket index")
if basket.empty:
    st.info("No basket snapshots yet — the pipeline builds history as it runs.")
else:
    st.altair_chart(basket_chart(basket), width="stretch")

st.divider()

# ---------------------------------------------------------------- products
st.subheader("Per-item trends")
st.markdown(
    " &nbsp;&nbsp; ".join(
        f'<span style="color:{c};font-size:1.1em">■</span> {m}'
        for m, c in COLORS.items()
    ),
    unsafe_allow_html=True,
)

if df.empty:
    st.info("No per-item history yet.")
else:
    # biggest movers first — most interesting even when history is thin
    products = sorted(df["product_name"].unique())
    ranked = []
    for product in products:
        series = df[df["product_name"] == product]
        latest, pct = pct_change(series, "avg_regular")
        ranked.append((product, series, latest, pct))
    ranked.sort(key=lambda r: abs(r[3]) if r[3] is not None else -1, reverse=True)

    n_cols = 5
    cols = st.columns(n_cols)
    for i, (product, series, latest, pct) in enumerate(ranked):
        with cols[i % n_cols]:
            with st.container(border=True):
                label = product if len(product) <= 32 else product[:31] + "…"
                st.metric(
                    label,
                    f"${latest:,.2f}" if latest is not None else "—",
                    delta=(f"{pct:+.1f}%" if pct is not None else None),
                    delta_color="inverse",
                    help=product,
                )
                st.altair_chart(mini_chart(series), width="stretch")

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("About")
    st.markdown(
        "**mycpi** tracks the real price of my recurring grocery basket instead of "
        "a national average.\n\n"
        "- **Source:** Kroger Products API, one fixed store\n"
        "- **Cadence:** hourly snapshot via cron\n"
        "- **Basket:** a fixed set of items; the index is only recorded when every "
        "item prices cleanly, so it always compares like with like\n"
        "- **Sale line** is the best (lowest) promo price seen that day"
    )
    st.divider()

    st.subheader("National reference")
    if cpi.empty:
        st.caption("No BLS data loaded yet.")
    else:
        st.altair_chart(cpi_chart(cpi), width="stretch")
        st.caption(
            f"BLS {CPI_SERIES_LABEL.lower()} ({CPI_SERIES}), monthly index. Shown on "
            "its own scale — it doesn't yet overlap the basket's date range, so the "
            "two aren't plotted together."
        )
    st.divider()
    st.caption(
        "Prices are point-in-time snapshots and may lag the store. "
        "Not affiliated with Kroger."
    )
