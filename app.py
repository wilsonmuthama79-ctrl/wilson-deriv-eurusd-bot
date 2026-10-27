
import json
import time
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import websocket

# =========================================================
# WILSON MUTHAMA KE
# DERIV EUR/USD LIVE MARKET ANALYSIS
# Analysis only. No trades are placed.
# =========================================================

WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"
SYMBOL = "frxEURUSD"

TIMEFRAMES = {
    "1 Minute": 60,
    "5 Minutes": 300,
    "15 Minutes": 900,
}

st.set_page_config(
    page_title="WILSON MUTHAMA KE | EUR/USD",
    page_icon="📈",
    layout="wide",
)

st.markdown("""
<style>
.stApp {
    background-color: #0b1120;
    color: #e5e7eb;
}
[data-testid="stMetric"] {
    background: #172033;
    border: 1px solid #29364c;
    padding: 12px;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

st.title("📈 WILSON MUTHAMA KE")
st.subheader("EUR/USD LIVE MARKET ANALYSIS")
st.caption(
    "Deriv live prices | 1m, 5m and 15m analysis | "
    "No automatic trading"
)

st.sidebar.header("Dashboard Settings")
refresh_seconds = st.sidebar.selectbox(
    "Refresh interval",
    [2, 3, 5],
    index=0,
    format_func=lambda x: f"{x} seconds",
)

if st.sidebar.button("Reload historical candles"):
    for key in ["history", "last_tick", "last_tick_received"]:
        st.session_state.pop(key, None)
    st.rerun()


def request_deriv(message, timeout=10):
    """Send one request to Deriv and return its response."""
    ws = websocket.create_connection(
        WS_URL,
        timeout=timeout,
        enable_multithread=True,
    )
    try:
        ws.send(json.dumps(message))
        deadline = time.time() + timeout

        while time.time() < deadline:
            response = json.loads(ws.recv())

            if response.get("error"):
                raise RuntimeError(
                    response["error"].get("message", "Deriv API error")
                )

            if response.get("msg_type") in (
                "candles", "history", "tick"
            ):
                return response

        raise TimeoutError("Deriv did not return data in time.")
    finally:
        ws.close()


def fetch_history(granularity, count=200):
    """Fetch real historical candles from Deriv."""
    response = request_deriv({
        "ticks_history": SYMBOL,
        "style": "candles",
        "granularity": granularity,
        "count": count,
        "end": "latest",
    })

    candles = response.get("candles", [])
    if not candles:
        raise RuntimeError("No historical candles were returned.")

    df = pd.DataFrame(candles)
    df["epoch"] = pd.to_numeric(df["epoch"])
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col])

    df = df.drop_duplicates("epoch").sort_values("epoch")
    return df.reset_index(drop=True)


def fetch_tick():
    """Receive a fresh EUR/USD quote from Deriv."""
    response = request_deriv({
        "ticks": SYMBOL,
        "subscribe": 1,
    })

    tick = response.get("tick")
    if not tick:
        raise RuntimeError("No live tick received.")

    return {
        "epoch": int(tick["epoch"]),
        "price": float(tick["quote"]),
        "bid": float(tick.get("bid", tick["quote"])),
        "ask": float(tick.get("ask", tick["quote"])),
    }


def update_current_candle(df, tick, granularity):
    """Update the active candle with the newest live price."""
    df = df.copy()
    bucket = (tick["epoch"] // granularity) * granularity
    price = tick["price"]

    if len(df) and int(df.iloc[-1]["epoch"]) == bucket:
        idx = df.index[-1]
        df.loc[idx, "high"] = max(float(df.loc[idx, "high"]), price)
        df.loc[idx, "low"] = min(float(df.loc[idx, "low"]), price)
        df.loc[idx, "close"] = price
    elif len(df) and int(df.iloc[-1]["epoch"]) < bucket:
        df.loc[len(df)] = {
            "epoch": bucket,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
        }

    return df.tail(250).reset_index(drop=True)


def calculate_indicators(df):
    df = df.copy()

    df["SMA20"] = df["close"].rolling(20).mean()
    df["SMA50"] = df["close"].rolling(50).mean()
    df["EMA12"] = df["close"].ewm(span=12, adjust=False).mean()
    df["EMA26"] = df["close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["MACD_signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()

    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    df.loc[(avg_loss == 0) & (avg_gain > 0), "RSI"] = 100
    df.loc[(avg_loss == 0) & (avg_gain == 0), "RSI"] = 50

    return df


def analyse(df):
    """Transparent indicator score, not a profit probability."""
    if len(df) < 55:
        return {
            "signal": "WAIT",
            "bull": 0,
            "bear": 0,
            "reasons": ["Collecting enough candles for analysis."],
            "rsi": None,
        }

    last = df.iloc[-1]
    bull = 0
    bear = 0
    reasons = []

    checks = [
        (
            last["SMA20"] > last["SMA50"],
            last["SMA20"] < last["SMA50"],
            "SMA20 versus SMA50",
        ),
        (
            last["EMA12"] > last["EMA26"],
            last["EMA12"] < last["EMA26"],
            "EMA12 versus EMA26",
        ),
        (
            last["MACD"] > last["MACD_signal"],
            last["MACD"] < last["MACD_signal"],
            "MACD versus signal line",
        ),
    ]

    for is_bull, is_bear, name in checks:
        if is_bull:
            bull += 1
            reasons.append(f"Bullish: {name}.")
        elif is_bear:
            bear += 1
            reasons.append(f"Bearish: {name}.")
        else:
            reasons.append(f"Neutral: {name}.")

    rsi = last["RSI"]
    if pd.notna(rsi):
        if 55 <= rsi < 70:
            bull += 1
            reasons.append("RSI supports bullish momentum.")
        elif 30 < rsi <= 45:
            bear += 1
            reasons.append("RSI supports bearish momentum.")
        elif rsi >= 70:
            reasons.append("RSI is high; bullish moves may be extended.")
        elif rsi <= 30:
            reasons.append("RSI is low; bearish moves may be extended.")
        else:
            reasons.append("RSI is neutral.")

    # Require at least 3 votes and a one-vote lead.
    if bull >= 3 and bull > bear:
        signal = "UPTRADE"
    elif bear >= 3 and bear > bull:
        signal = "DOWNTRADE"
    else:
        signal = "WAIT"

    return {
        "signal": signal,
        "bull": bull,
        "bear": bear,
        "reasons": reasons,
        "rsi": float(rsi) if pd.notna(rsi) else None,
    }


def draw_chart(df, title):
    chart = df.copy()
    chart["time"] = pd.to_datetime(chart["epoch"], unit="s", utc=True)

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=chart["time"],
        open=chart["open"],
        high=chart["high"],
        low=chart["low"],
        close=chart["close"],
        name="EUR/USD",
    ))
    fig.add_trace(go.Scatter(
        x=chart["time"], y=chart["SMA20"],
        mode="lines", name="SMA20",
    ))
    fig.add_trace(go.Scatter(
        x=chart["time"], y=chart["SMA50"],
        mode="lines", name="SMA50",
    ))
    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=400,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=45, b=10),
    )
    return fig


# Load historical candles once per session.
if "history" not in st.session_state:
    st.session_state.history = {}
    for label, seconds in TIMEFRAMES.items():
        try:
            st.session_state.history[label] = fetch_history(seconds)
        except Exception as exc:
            st.error(f"Could not load {label} history: {exc}")

if "last_tick" not in st.session_state:
    st.session_state.last_tick = None
if "last_tick_received" not in st.session_state:
    st.session_state.last_tick_received = None


@st.fragment(run_every=refresh_seconds)
def live_market():
    try:
        tick = fetch_tick()
        st.session_state.last_tick = tick
        st.session_state.last_tick_received = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        for label, seconds in TIMEFRAMES.items():
            if label in st.session_state.history:
                st.session_state.history[label] = update_current_candle(
                    st.session_state.history[label], tick, seconds
                )

        st.success("CONNECTED — fresh EUR/USD tick received")

    except Exception as exc:
        st.warning(f"Live feed issue: {exc}")

    tick = st.session_state.last_tick
    if not tick:
        st.info("Waiting for the first live EUR/USD tick.")
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("LIVE EUR/USD", f'{tick["price"]:.5f}')
    m2.metric("BID", f'{tick["bid"]:.5f}')
    m3.metric("ASK", f'{tick["ask"]:.5f}')
    m4.metric("SPREAD", f'{tick["ask"] - tick["bid"]:.5f}')

    st.caption(
        f'Last received: {st.session_state.last_tick_received}'
    )

    results = {}
    for label in TIMEFRAMES:
        raw = st.session_state.history.get(label)
        if raw is None or raw.empty:
            continue
        data = calculate_indicators(raw)
        results[label] = (data, analyse(data))

    st.subheader("Trade Direction Signals")
    cols = st.columns(3)

    for col, label in zip(cols, TIMEFRAMES):
        with col:
            if label not in results:
                st.warning(f"{label}: no data")
                continue

            data, result = results[label]
            signal = result["signal"]

            if signal == "UPTRADE":
                st.success(f"🟢 {label}: UPTRADE")
            elif signal == "DOWNTRADE":
                st.error(f"🔴 {label}: DOWNTRADE")
            else:
                st.warning(f"🟡 {label}: WAIT")

            st.write(
                f'Bullish votes: {result["bull"]} | '
                f'Bearish votes: {result["bear"]}'
            )

            rsi = result["rsi"]
            st.write(
                f"RSI: {rsi:.2f}" if rsi is not None else "RSI: calculating"
            )

    signals = [
        results[label][1]["signal"]
        for label in TIMEFRAMES
        if label in results
    ]

    if len(signals) == 3 and signals[0] == signals[1] == signals[2]:
        st.info(f"All three timeframes agree: {signals[0]}")
    else:
        st.info("Timeframes do not fully agree — use caution.")

    selected = st.selectbox(
        "Chart to view",
        list(TIMEFRAMES.keys()),
        index=1,
        key="chart_timeframe",
    )

    if selected in results:
        data, result = results[selected]
        st.plotly_chart(
            draw_chart(data, f"EUR/USD — {selected}"),
            use_container_width=True,
        )

        st.subheader(f"{selected} Analysis Reasons")
        for reason in result["reasons"]:
            st.write(f"- {reason}")

        recent = data.tail(30)
        a, b = st.columns(2)
        a.metric("Recent support estimate", f'{recent["low"].min():.5f}')
        b.metric("Recent resistance estimate", f'{recent["high"].max():.5f}')

        with st.expander("Recent candles"):
            st.dataframe(
                data.tail(20),
                use_container_width=True,
                hide_index=True,
            )


live_market()

st.divider()
st.caption(
    "WILSON MUTHAMA KE | Technical analysis only. "
    "UPTRADE/DOWNTRADE are indicator-based directions, not guarantees. "
    "No trades are placed."
)
