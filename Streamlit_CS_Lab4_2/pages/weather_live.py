import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import time
from collections import deque
from datetime import datetime, timedelta

st.set_page_config(page_title="Weather Live (Open-Meteo)", page_icon="🌤️", layout="wide")
st.title("🌤️ Open-Meteo — Temperature Over Time")
st.caption("Denver current weather, cached + short rolling history + auto-refresh.")

# ---------- Config ---------- #
lat, lon = 39.7392, -104.9903  # Denver
WURL = (
    f"https://api.open-meteo.com/v1/forecast?"
    f"latitude={lat}&longitude={lon}&current=temperature_2m,wind_speed_10m"
)
HEADERS = {"User-Agent": "msudenver-dataviz-class/1.0", "Accept": "application/json"}

# ---------- Cached fetch ---------- #
@st.cache_data(ttl=600, show_spinner=False)  # 10 minutes cache
def get_weather():
    try:
        r = requests.get(WURL, timeout=10, headers=HEADERS)
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After", "a bit")
            return None, f"429 Too Many Requests — try again after {retry_after}s"
        r.raise_for_status()
        j = r.json()["current"]
        df = pd.DataFrame([{
            "time": pd.to_datetime(j["time"]),
            "temperature": float(j["temperature_2m"]),
            "wind": float(j["wind_speed_10m"])
        }])
        return df, None
    except requests.RequestException as e:
        return None, f"Network/HTTP error: {e}"

# ---------- Auto Refresh Controls ---------- #
st.subheader("🔁 Auto Refresh Settings")
col_a, col_b, col_c = st.columns([1,1,2])
with col_a:
    refresh_sec = st.slider("Refresh every (sec)", 10, 120, 30)
with col_b:
    auto_refresh = st.toggle("Enable auto-refresh", value=False)
with col_c:
    st.caption(f"Last refreshed at: {time.strftime('%H:%M:%S')}")

if st.button("Manual refresh now", use_container_width=False):
    get_weather.clear()
    st.rerun()

# ---------- Short rolling history ---------- #
WINDOW_HOURS = 6  # keep last 6 hours of samples
if "weather_history" not in st.session_state:
    st.session_state.weather_history = deque() 

def prune_weather():
    cutoff = datetime.utcnow() - timedelta(hours=WINDOW_HOURS)
    while st.session_state.weather_history and st.session_state.weather_history[0]["ts"] < cutoff:
        st.session_state.weather_history.popleft()

# ---------- Fetch & Display ---------- #
st.subheader("Current Reading")

wdf, werr = get_weather()
if werr:
    st.warning(werr)
    #Provide a subtle fallback (fake-ish record stamped 'now' so the page doesn't die)
    now = datetime.utcnow()
    wdf = pd.DataFrame([{"time": pd.to_datetime(now), "temperature": float("nan"), "wind": float("nan")}])

st.dataframe(wdf, use_container_width=True)

#Append to history
ts = pd.to_datetime(wdf["time"].iloc[0]).to_pydatetime()
temp = float(wdf["temperature"].iloc[0]) if pd.notna(wdf["temperature"].iloc[0]) else None
wind = float(wdf["wind"].iloc[0]) if pd.notna(wdf["wind"].iloc[0]) else None

st.session_state.weather_history.append({
    "ts": ts,
    "temperature": temp,
    "wind": wind
})
prune_weather()

hist = pd.DataFrame(list(st.session_state.weather_history)) if st.session_state.weather_history else pd.DataFrame()

# ---------- Metrics ---------- #
st.subheader("Metrics")
col1, col2 = st.columns(2)

#Temperature metric with delta from previous reading
if not hist.empty:
    current_t = hist["temperature"].iloc[-1]
    prev_t = hist["temperature"].iloc[-2] if len(hist) > 1 else None
    t_delta = None if (prev_t is None or pd.isna(prev_t) or pd.isna(current_t)) else (current_t - prev_t)

    with col1:
        st.metric("Temperature (°C)", f"{current_t:.1f}" if pd.notna(current_t) else "—",
                  delta=(f"{t_delta:+.1f}°" if t_delta is not None else None))

    current_w = hist["wind"].iloc[-1]
    prev_w = hist["wind"].iloc[-2] if len(hist) > 1 else None
    w_delta = None if (prev_w is None or pd.isna(prev_w) or pd.isna(current_w)) else (current_w - prev_w)

    with col2:
        st.metric("Wind (m/s)", f"{current_w:.1f}" if pd.notna(current_w) else "—",
                  delta=(f"{w_delta:+.1f}" if w_delta is not None else None))
else:
    st.info("No readings yet. Enable auto-refresh to start building a history.")

# ---------- Temperature over time (LINE) ---------- #
st.subheader(f"Temperature over time (last ~{WINDOW_HOURS} hours)")
if not hist.empty and hist["temperature"].notna().any():
    tdf = hist.dropna(subset=["temperature"])
    fig = px.line(tdf, x="ts", y="temperature", markers=True, title="Live Temperature (°C)")
    fig.update_layout(xaxis_title="Time (UTC)", yaxis_title="°C", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No temperature values yet to plot.")

#Wind line chart
with st.expander("Show wind over time"):
    if not hist.empty and hist["wind"].notna().any():
        wdf2 = hist.dropna(subset=["wind"])
        fig2 = px.line(wdf2, x="ts", y="wind", markers=True, title="Live Wind Speed (m/s)")
        fig2.update_layout(xaxis_title="Time (UTC)", yaxis_title="m/s", hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.caption("No wind values yet to plot.")

# ---------- Auto-refresh ---------- #
if auto_refresh:
    time.sleep(refresh_sec)
    get_weather.clear()
    st.rerun()
