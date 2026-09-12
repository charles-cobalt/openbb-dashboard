import os
import sys
import zipfile

# Streamlit Cloud runs the app as a user without write access to site-packages.
# OpenBB's auto-build writes there on first import, so we ship the pre-built
# OpenBB package artifacts in openbb_pkg.zip, extract to a writable dir, and
# disable auto-build.
os.environ.setdefault("OPENBB_AUTO_BUILD", "false")
_PKG_DIR = "/tmp/openbb_pkg"
if not os.path.exists(os.path.join(_PKG_DIR, "openbb", "__init__.py")):
    os.makedirs(_PKG_DIR, exist_ok=True)
    with zipfile.ZipFile(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "openbb_pkg.zip")
    ) as z:
        z.extractall(_PKG_DIR)
sys.path.insert(0, _PKG_DIR)

import warnings
warnings.filterwarnings("ignore")

from datetime import date
from dateutil.relativedelta import relativedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from openbb import obb

st.set_page_config(page_title="OpenBB Market Dashboard", layout="wide")

WATCHLIST = ["SPY", "QQQ", "DIA", "AAPL", "NVDA", "MSFT", "TSLA", "AMD"]
PERIODS = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "5Y": 60}

st.title("OpenBB Market Dashboard")
st.caption(
    "Built on the open-source OpenBB Platform (github.com/OpenBB-finance/OpenBB). "
    "Live market data via the OpenBB yfinance provider - no API keys, no cost."
)


@st.cache_data(ttl=300, show_spinner=False)
def get_quote(symbol: str) -> dict:
    """Live quote via OpenBB. yfinance quote payloads for ETFs omit
    last_price, so backfill it from the latest daily closes. Retries on
    transient errors (cold-start throttling from cloud IPs)."""
    import time

    last_err: Exception | None = None
    q: dict | None = None
    for _ in range(3):
        try:
            df = obb.equity.price.quote(symbol, provider="yfinance").to_dataframe()
            q = df.iloc[0].to_dict()
            if q.get("last_price") is not None:
                return q
            break
        except Exception as e:  # noqa: PERF203
            last_err = e
            time.sleep(2)

    h = obb.equity.price.historical(
        symbol, provider="yfinance", interval="1d"
    ).to_dataframe()
    closes = h["close"].dropna()
    if len(closes) < 2:
        if q is not None:
            return q
        raise last_err  # type: ignore[misc]
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    if q is None:
        q = {"symbol": symbol, "name": symbol, "currency": ""}
    q["last_price"] = last
    if not q.get("prev_close"):
        q["prev_close"] = prev
    return q


@st.cache_data(ttl=900, show_spinner=False)
def get_history(symbol: str, months: int) -> pd.DataFrame:
    start = date.today() - relativedelta(months=months)
    df = obb.equity.price.historical(
        symbol, provider="yfinance", interval="1d", start_date=start.isoformat()
    ).to_dataframe()
    return df.reset_index()


@st.cache_data(ttl=900, show_spinner=False)
def get_news(symbol: str) -> pd.DataFrame:
    df = obb.news.company(symbol, provider="yfinance", limit=12).to_dataframe()
    return df.reset_index()


def change_badge(q: dict):
    last, prev = q.get("last_price"), q.get("prev_close")
    if last is None or prev in (None, 0):
        return None, None
    chg = last - prev
    return last, chg / prev * 100


# --- Watchlist strip ---
st.subheader("Watchlist")
cols = st.columns(len(WATCHLIST))
for col, sym in zip(cols, WATCHLIST):
    with col:
        try:
            q = get_quote(sym)
            last, pct = change_badge(q)
            if last is None:
                st.metric(sym, "n/a")
            else:
                st.metric(sym, f"{last:,.2f}", f"{pct:+.2f}%")
        except Exception:
            st.metric(sym, "n/a")

st.divider()

# --- Symbol explorer ---
left, right = st.columns([1, 3])
with left:
    symbol = st.text_input("Ticker symbol", value="AAPL").strip().upper() or "AAPL"
    period_label = st.radio("History", list(PERIODS.keys()), index=3, horizontal=True)
months = PERIODS[period_label]

try:
    q = get_quote(symbol)
except Exception:
    st.error(f"No data found for '{symbol}'. Try another ticker.")
    st.stop()

last, pct = change_badge(q)
name = q.get("name") or symbol
header = f"### {name} ({q.get('symbol', symbol)})"
st.markdown(header)
if last is not None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last", f"{last:,.2f} {q.get('currency', '')}", f"{pct:+.2f}% vs prev close")
    c2.metric("Day range", f"{q.get('low', 0):,.2f} - {q.get('high', 0):,.2f}")
    c3.metric("Volume", f"{int(q.get('volume') or 0):,}")
    c4.metric("52w range", f"{q.get('year_low', 0):,.2f} - {q.get('year_high', 0):,.2f}")

try:
    hist = get_history(symbol, months)
except Exception:
    hist = pd.DataFrame()

if hist.empty:
    st.warning("No historical data returned for this ticker/period.")
else:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(
        x=hist["date"], open=hist["open"], high=hist["high"],
        low=hist["low"], close=hist["close"], name=symbol,
    ), row=1, col=1)
    fig.add_trace(go.Bar(x=hist["date"], y=hist["volume"], name="Volume",
                         marker_color="#636efa"), row=2, col=1)
    fig.update_layout(height=560, xaxis_rangeslider_visible=False,
                      margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

st.subheader(f"Latest news - {symbol}")
try:
    news = get_news(symbol)
    for _, row in news.iterrows():
        ts = row.get("date")
        when = ts.strftime("%b %d, %Y %H:%M UTC") if hasattr(ts, "strftime") else ""
        st.markdown(f"- [{row['title']}]({row['url']})  \n  {when}")
except Exception:
    st.info("No news available for this ticker right now.")

st.divider()
st.caption(
    "Data: Yahoo Finance through the OpenBB Platform yfinance provider. "
    "Hosted free on Streamlit Community Cloud. Not investment advice."
)
