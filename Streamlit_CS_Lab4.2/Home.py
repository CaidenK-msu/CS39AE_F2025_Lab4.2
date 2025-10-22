import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time
from collections import deque
from datetime import datetime, timedelta

# ---------- Page & Style ----------
st.set_page_config(page_title="Live API Demo (Simple)", page_icon="📡", layout="wide")
st.markdown("""
    <style>
      [data-testid="stPlotlyChart"], .stPlotlyChart, .stElementContainer {
        transition: none !important;
        opacity: 1 !important;
      }
    </style>
""", unsafe_allow_html=True)

st.title("📡 Simple Live Data Demo (CoinGecko)")
st.caption("Live polling with cache, short history, auto-refresh, and safe fallbacks.")

# ---------- Config ----------
COINS = ["bitcoin", "ethereum"]
VS = "usd"
HEADERS = {"User-Agent": "msudenver-dataviz-class/1.0", "Accept": "application/json"}

def build_url(ids):
    return f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(ids)}&vs_currencies={VS}"

API_URL = build_url(COINS)

# Tiny sample to keep the demo working even if the API is rate-limiting
SAMPLE_DF = pd.DataFrame(
    [{"coin": "bitcoin", VS: 68000}, {"coin": "ethereum", VS: 3500}]
)

# ---------- CACHED FETCH ----------
@st.cache_data(ttl=300, show_spinner=False)   # Cache for 5 minutes
def fetch_prices(url: str):
    """Return (df, error_message). Never raise. Safe for beginners."""
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "a bit")
            return None, f"429 Too Many Requests — try again after {retry_after}s"
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data).T.reset_index().rename(columns={"index": "coin"})
        return df, None
    except requests.RequestException as e:
        return None, f"Network/HTTP error: {e}"

# ---------- Auto Refresh Controls ----------
st.subheader("🔁 Auto Refresh Settings")
col_a, col_b, col_c = st.columns([1,1,2])
with col_a:
    refresh_sec = st.slider("Refresh every (sec)", 10, 120, 30)
with col_b:
    auto_refresh = st.toggle("Enable auto-refresh", value=False)
with col_c:
    st.caption(f"Last refreshed at: {time.strftime('%H:%M:%S')}")

# Manual refresh button (optional)
if st.button("Manual refresh now", use_container_width=False):
    fetch_prices.clear()
    st.rerun()

# ---------- Short rolling history in session_state ----------
# We'll keep a deque of records (timestamp, coin, price), limited by time window.
WINDOW_MINUTES = 30  # keep only last 30 minutes of samples

if "price_history" not in st.session_state:
    st.session_state.price_history = deque()  # store dicts: {"ts": datetime, "coin": str, "price": float}

def prune_history():
    cutoff = datetime.utcnow() - timedelta(minutes=WINDOW_MINUTES)
    while st.session_state.price_history and st.session_state.price_history[0]["ts"] < cutoff:
        st.session_state.price_history.popleft()

# ---------- MAIN VIEW ----------
st.subheader("Prices")

df, err = fetch_prices(API_URL)
if err:
    st.warning(f"{err}\nShowing sample data so the demo continues.")
    df = SAMPLE_DF.copy()

# Show current snapshot table
st.dataframe(df, use_container_width=True)

# Append to history
now = datetime.utcnow()
for _, row in df.iterrows():
    st.session_state.price_history.append({
        "ts": now,
        "coin": row["coin"],
        "price": float(row[VS])
    })
prune_history()

# Build a tidy DataFrame from history for plotting
if len(st.session_state.price_history) > 0:
    hist_df = pd.DataFrame(list(st.session_state.price_history))
else:
    hist_df = pd.DataFrame(columns=["ts", "coin", "price"])

# ---------- Metrics ----------
st.subheader("Metrics")
mcols = st.columns(len(COINS))
for i, coin in enumerate(COINS):
    cdf = hist_df[hist_df["coin"] == coin].sort_values("ts")
    current = cdf["price"].iloc[-1] if len(cdf) else None
    prev = cdf["price"].iloc[-2] if len(cdf) > 1 else None
    delta = None if (current is None or prev is None) else (current - prev)
    with mcols[i]:
        st.metric(
            label=f"{coin.capitalize()} ({VS.upper()})",
            value=f"{current:,.2f}" if current is not None else "—",
            delta=(f"{delta:,.2f}" if delta is not None else None)
        )

# ---------- Chart (line over time) ----------
st.subheader(f"Time Series (last ~{WINDOW_MINUTES} min)")
if not hist_df.empty:
    fig = px.line(
        hist_df,
        x="ts", y="price", color="coin",
        markers=True,
        title=f"Live {VS.upper()} prices"
    )
    fig.update_layout(xaxis_title="Time (UTC)", yaxis_title=f"Price ({VS.upper()})", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No history yet. Enable auto-refresh to start building a history.")

# ---------- Auto-refresh: wait, clear cache to force fresh call, rerun ----------
if auto_refresh:
    time.sleep(refresh_sec)
    fetch_prices.clear()  # clear cache so next run refetches immediately
    st.rerun()
