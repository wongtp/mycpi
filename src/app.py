import streamlit as st
import pandas as pd
import psycopg
from dotenv import load_dotenv
import altair as alt

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

# ---------------------------------------------------------------- KPI row
if not basket.empty:
    current = basket["basket_price"].iloc[-1]
    first = basket["basket_price"].iloc[0]
    since_start = current - first
    prev = basket["basket_price"].iloc[-2] if len(basket) > 1 else None

    k1, k2, k3, k4 = st.columns(4)
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
    st.caption(
        "Prices are point-in-time snapshots and may lag the store. "
        "Not affiliated with Kroger."
    )
