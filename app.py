"""OpenBB Workspace - community recreation.

A self-hosted recreation of the OpenBB Workspace experience running on the
real open-source OpenBB Open Data Platform (ODP) engine
(github.com/OpenBB-finance/OpenBB). Market data via OpenBB's yfinance
provider - no API keys, no cost.

Visual language uses design tokens from OpenBB's MIT-licensed design-system
(github.com/OpenBB-finance/design-system). Unofficial; not affiliated with
OpenBB. Not investment advice.
"""

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

from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from openbb import obb

st.set_page_config(
    page_title="OpenBB Workspace",
    page_icon=":material/monitoring:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# OpenBB Workspace design language (tokens from the MIT-licensed design-system)
# ---------------------------------------------------------------------------
C = {
    "bg": "#131313",          # grey.850 dark background
    "panel": "#1F1E23",       # dark.850 widget surface
    "panel_alt": "#212126",   # dark.800
    "border": "#2A2A31",      # dark.700
    "border_soft": "#24242A", # dark.750
    "text": "#EAEAEA",        # grey.100 foreground
    "muted": "#A2A2A2",       # grey.400
    "faint": "#808080",       # grey.500
    "accent": "#00AAFF",      # light-blue.500
    "up": "#22C55E",          # success.500
    "down": "#EF4444",        # danger.500
    "sidebar": "#0E0E11",
}

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', system-ui, sans-serif;
}}
.stApp {{ background-color: {C['bg']}; }}
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: rgba(0,0,0,0); }}

/* Sidebar */
section[data-testid="stSidebar"] {{
    background-color: {C['sidebar']};
    border-right: 1px solid {C['border']};
}}
section[data-testid="stSidebar"] > div {{ padding-top: 1.2rem; }}

/* Widget cards */
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div > .ws-widget) {{
    background-color: {C['panel']};
    border: 1px solid {C['border']};
    border-radius: 8px;
    padding: 0.35rem 0.9rem 0.9rem 0.9rem;
}}
.ws-widget-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 0.45rem 0.1rem 0.55rem 0.1rem;
    border-bottom: 1px solid {C['border_soft']};
    margin-bottom: 0.6rem;
}}
.ws-widget-title {{
    font-size: 0.82rem; font-weight: 600; color: {C['text']};
    letter-spacing: 0.01em;
}}
.ws-widget-tag {{
    font-size: 0.72rem; color: {C['muted']};
    background: {C['border_soft']}; border-radius: 4px; padding: 1px 7px;
}}
.ws-kv {{ display: flex; justify-content: space-between; padding: 4.5px 2px;
    font-size: 0.82rem; border-bottom: 1px solid {C['border_soft']}; }}
.ws-kv:last-child {{ border-bottom: none; }}
.ws-kv span:first-child {{ color: {C['muted']}; }}
.ws-kv span:last-child {{ color: {C['text']}; font-weight: 500; }}
.ws-logo {{
    font-size: 1.25rem; font-weight: 700; letter-spacing: 0.35em;
    color: {C['text']};
}}
.ws-section {{
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.12em;
    color: {C['faint']}; margin: 1.1rem 0 0.25rem 0;
}}
.ws-lib-item {{
    font-size: 0.85rem; color: {C['muted']}; padding: 2px 0;
}}
.ws-quote-name {{ font-size: 1.05rem; font-weight: 600; color: {C['text']}; }}
.ws-quote-sub {{ font-size: 0.78rem; color: {C['muted']}; }}
.ws-quote-price {{ font-size: 2.0rem; font-weight: 700; color: {C['text']}; }}
.ws-badge {{ font-size: 0.85rem; font-weight: 600; border-radius: 5px;
    padding: 2px 8px; }}
.ws-crumb {{ font-size: 0.75rem; color: {C['faint']}; margin-bottom: 0.4rem; }}
.ws-news-title {{ font-size: 0.88rem; font-weight: 600; }}
.ws-news-meta {{ font-size: 0.74rem; color: {C['faint']}; }}
.ws-news-sum {{ font-size: 0.8rem; color: {C['muted']}; }}
a {{ color: {C['accent']}; }}

/* tighter default gaps */
div[data-testid="stHorizontalBlock"] {{ gap: 0.9rem; }}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Data layer - real OpenBB ODP calls (yfinance provider, free, no keys)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def get_quote(symbol: str) -> dict:
    """Live quote via OpenBB. yfinance quote payloads for ETFs, indices,
    futures and FX omit last_price, so backfill from latest daily closes."""
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
    if q is None or not isinstance(q, dict):
        q = {"symbol": symbol, "name": symbol, "currency": ""}
    q["last_price"] = float(closes.iloc[-1])
    if not q.get("prev_close"):
        q["prev_close"] = float(closes.iloc[-2])
    return q


@st.cache_data(ttl=900, show_spinner=False)
def get_history(symbol: str, months: int = 12, interval: str = "1d") -> pd.DataFrame:
    start = date.today() - relativedelta(months=months)
    df = obb.equity.price.historical(
        symbol, provider="yfinance", interval=interval, start_date=start.isoformat()
    ).to_dataframe()
    return df.reset_index()


@st.cache_data(ttl=300, show_spinner=False)
def get_intraday(symbol: str, days: int = 2, interval: str = "1m") -> pd.DataFrame:
    start = date.today() - timedelta(days=days)
    df = obb.equity.price.historical(
        symbol, provider="yfinance", interval=interval, start_date=start.isoformat()
    ).to_dataframe()
    return df.reset_index()


@st.cache_data(ttl=900, show_spinner=False)
def get_news(symbol: str, limit: int = 10) -> pd.DataFrame:
    df = obb.news.company(symbol, provider="yfinance", limit=limit).to_dataframe()
    return df.reset_index()


@st.cache_data(ttl=600, show_spinner=False)
def get_metrics(symbol: str) -> dict:
    df = obb.equity.fundamental.metrics(symbol, provider="yfinance").to_dataframe()
    return df.iloc[0].to_dict()


@st.cache_data(ttl=86400, show_spinner=False)
def get_profile(symbol: str) -> dict:
    df = obb.equity.profile(symbol, provider="yfinance").to_dataframe()
    return df.iloc[0].to_dict()


@st.cache_data(ttl=3600, show_spinner=False)
def get_statement(symbol: str, kind: str, limit: int = 4) -> pd.DataFrame:
    fn = {
        "income": obb.equity.fundamental.income,
        "balance": obb.equity.fundamental.balance,
        "cash": obb.equity.fundamental.cash,
    }[kind]
    df = fn(symbol, provider="yfinance", period="annual", limit=limit).to_dataframe()
    return df.reset_index()


@st.cache_data(ttl=600, show_spinner=False)
def get_movers(kind: str, limit: int = 50) -> pd.DataFrame:
    fn = {
        "gainers": obb.equity.discovery.gainers,
        "losers": obb.equity.discovery.losers,
        "active": obb.equity.discovery.active,
    }[kind]
    df = fn(provider="yfinance").to_dataframe()
    return df.head(limit).reset_index()


@st.cache_data(ttl=3600, show_spinner=False)
def get_etf_info(symbol: str) -> dict:
    df = obb.etf.info(symbol, provider="yfinance").to_dataframe()
    return df.iloc[0].to_dict()


# ---------------------------------------------------------------------------
# Formatting + UI helpers
# ---------------------------------------------------------------------------

def fmt_big(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    v = float(v)
    for cut, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= cut:
            return f"{v / cut:,.2f} {suf}"
    return f"{v:,.2f}"


def fmt_num(v, nd: int = 2) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{float(v):,.{nd}f}"


def fmt_pct(v, signed: bool = True) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    return f"{float(v):+.2f}%" if signed else f"{float(v):.2f}%"


def badge(pct: float | None, chg: float | None = None) -> str:
    if pct is None or pd.isna(pct):
        return ""
    col = C["up"] if pct >= 0 else C["down"]
    arrow = "▲" if pct >= 0 else "▼"
    chg_txt = f"{chg:+,.2f}  " if chg is not None and not pd.isna(chg) else ""
    return (
        f"<span class='ws-badge' style='color:{col};background:{col}1A;'>"
        f"{arrow} {chg_txt}{pct:+.2f}%</span>"
    )


def widget_header(title: str, tag: str = ""):
    tag_html = f"<span class='ws-widget-tag'>{tag}</span>" if tag else "<span></span>"
    st.markdown(
        f"<div class='ws-widget'><div class='ws-widget-header'>"
        f"<span class='ws-widget-title'>{title}</span>{tag_html}</div></div>",
        unsafe_allow_html=True,
    )


def kv_rows(rows: list[tuple[str, str]]):
    html = "".join(
        f"<div class='ws-kv'><span>{k}</span><span>{v}</span></div>" for k, v in rows
    )
    st.markdown(f"<div>{html}</div>", unsafe_allow_html=True)


def ws_fig(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", color=C["muted"], size=11),
        margin=dict(l=6, r=6, t=10, b=6),
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=10)),
    )
    fig.update_xaxes(gridcolor=C["border_soft"], zerolinecolor=C["border_soft"])
    fig.update_yaxes(gridcolor=C["border_soft"], zerolinecolor=C["border_soft"])
    return fig


def candlestick_chart(df: pd.DataFrame, symbol: str, height: int = 440,
                      show_ma: bool = False) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.78, 0.22], vertical_spacing=0.02)
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"],
        close=df["close"], name=symbol,
        increasing_line_color=C["up"], decreasing_line_color=C["down"],
    ), row=1, col=1)
    if show_ma and len(df) > 50:
        fig.add_trace(go.Scatter(x=df["date"], y=df["close"].rolling(50).mean(),
                                 name="MA 50", line=dict(color=C["accent"], width=1.2)),
                      row=1, col=1)
    if show_ma and len(df) > 200:
        fig.add_trace(go.Scatter(x=df["date"], y=df["close"].rolling(200).mean(),
                                 name="MA 200", line=dict(color="#EF7D00", width=1.2)),
                      row=1, col=1)
    colors = [C["up"] if c >= o else C["down"] for o, c in zip(df["open"], df["close"])]
    fig.add_trace(go.Bar(x=df["date"], y=df["volume"], name="Volume",
                         marker_color=colors, opacity=0.6), row=2, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False)
    return ws_fig(fig, height)


def stmt_table(df: pd.DataFrame, wanted: list[tuple[str, str]]) -> pd.DataFrame:
    """Transpose an ODP statement frame: line items as rows, periods as cols."""
    out = {}
    periods = df["period_ending"].tolist()
    for label, col in wanted:
        if col in df.columns:
            out[label] = [fmt_big(v) for v in df[col].tolist()]
    tbl = pd.DataFrame(out, index=[str(p)[:10] for p in periods]).T
    return tbl


INCOME_ITEMS = [
    ("Total revenue", "total_revenue"),
    ("Cost of revenue", "cost_of_revenue"),
    ("Gross profit", "gross_profit"),
    ("R&D expense", "research_and_development_expense"),
    ("SG&A expense", "selling_general_and_admin_expense"),
    ("Operating expense", "operating_expense"),
    ("Operating income", "operating_income"),
    ("Pre-tax income", "total_pre_tax_income"),
    ("Net income", "net_income"),
]
BALANCE_ITEMS = [
    ("Cash & equivalents", "cash_and_cash_equivalents"),
    ("Short-term investments", "short_term_investments"),
    ("Total current assets", "total_current_assets"),
    ("Total assets", "total_assets"),
    ("Total current liabilities", "total_current_liabilities"),
    ("Total liabilities", "total_liabilities"),
    ("Total equity", "total_equity"),
    ("Stockholders' equity", "stockholders_equity"),
]
CASH_ITEMS = [
    ("Net income (cont. ops)", "net_income_from_continuing_operations"),
    ("D&A", "depreciation_and_amortization"),
    ("Operating cash flow", "operating_cash_flow"),
    ("Investing cash flow", "investing_cash_flow"),
    ("Financing cash flow", "financing_cash_flow"),
    ("Capital expenditure", "capital_expenditure"),
    ("Free cash flow", "free_cash_flow"),
    ("End cash position", "end_cash_position"),
]

# ---------------------------------------------------------------------------
# Sidebar - Workspace navigation replica
# ---------------------------------------------------------------------------
if "symbol" not in st.session_state:
    st.session_state.symbol = "AAPL"
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["SPY", "QQQ", "DIA", "AAPL", "NVDA", "MSFT", "TSLA", "AMD"]

with st.sidebar:
    st.markdown("<div class='ws-logo'>OPENBB</div>", unsafe_allow_html=True)
    st.caption("Workspace · community recreation")

    q = st.text_input("Search", placeholder="Search tickers   ⌘K",
                      label_visibility="collapsed")
    if q and q.strip().upper() != st.session_state.symbol:
        st.session_state.symbol = q.strip().upper()

    st.markdown("<div class='ws-section'>LIBRARY</div>", unsafe_allow_html=True)
    st.markdown("<div class='ws-lib-item'>▦ &nbsp;Widgets</div>", unsafe_allow_html=True)
    st.markdown("<div class='ws-lib-item' style='opacity:0.45'>✦ &nbsp;AI "
                "<span style='font-size:0.68rem'>(hosted Copilot - not available "
                "in this recreation)</span></div>", unsafe_allow_html=True)

    st.markdown("<div class='ws-section'>MY DASHBOARDS</div>", unsafe_allow_html=True)
    dashboard = st.radio(
        "Dashboards",
        ["Equity Dashboard", "Charting", "News", "World Economics", "Screener", "Watchlist"],
        label_visibility="collapsed",
    )

    st.markdown(
        "<div style='position:fixed;bottom:12px;font-size:0.7rem;color:#5A5A5A;"
        "max-width:220px'>Runs on the real open-source OpenBB ODP engine. "
        "Data: Yahoo Finance via OpenBB · yfinance provider. Unofficial "
        "recreation. Not investment advice.</div>",
        unsafe_allow_html=True,
    )

SYMBOL = st.session_state.symbol

st.markdown(
    f"<div class='ws-crumb'>Dashboards&nbsp;&nbsp;/&nbsp;&nbsp;{dashboard}</div>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

def quote_change(q: dict):
    last, prev = q.get("last_price"), q.get("prev_close")
    if last is None or prev in (None, 0):
        return None, None, None
    chg = last - prev
    return last, chg, chg / prev * 100


def quote_header(symbol: str):
    try:
        q = get_quote(symbol)
    except Exception:
        st.error(f"No data found for '{symbol}'. Try another ticker.")
        return
    last, chg, pct = quote_change(q)
    name = q.get("name") or symbol
    exch = q.get("exchange") or ""
    cur = q.get("currency") or ""
    with st.container(border=True):
        widget_header("Quote", symbol)
        c1, c2, c3 = st.columns([3, 2, 5])
        with c1:
            st.markdown(
                f"<div class='ws-quote-name'>{name}</div>"
                f"<div class='ws-quote-sub'>{q.get('symbol', symbol)}"
                f"{' · ' + str(exch) if exch else ''}"
                f"{' · ' + str(cur) if cur else ''}</div>",
                unsafe_allow_html=True,
            )
        with c2:
            price_txt = fmt_num(last) if last is not None else "-"
            st.markdown(
                f"<span class='ws-quote-price'>{price_txt}</span> {badge(pct, chg)}",
                unsafe_allow_html=True,
            )
        with c3:
            kv_rows([
                ("Open", fmt_num(q.get("open"))),
                ("Day range", f"{fmt_num(q.get('low'))} - {fmt_num(q.get('high'))}"),
                ("Prev close", fmt_num(q.get("prev_close"))),
                ("Volume", fmt_big(q.get("volume"))),
            ])


def key_metrics_widget(symbol: str):
    with st.container(border=True):
        widget_header("Key Metrics", symbol)
        try:
            q = get_quote(symbol)
        except Exception:
            q = {}
        try:
            m = get_metrics(symbol)
        except Exception:
            m = {}
        if not q and not m:
            st.warning("Metrics unavailable right now.")
            return
        kv_rows([
            ("Beta", fmt_num(m.get("beta"))),
            ("Vol Avg", fmt_big(q.get("volume_average"))),
            ("Market Cap", fmt_big(m.get("market_cap"))),
            ("Range", f"{fmt_num(q.get('low'), 0)} - {fmt_num(q.get('high'), 0)}"),
            ("52-week High", fmt_num(q.get("year_high"))),
            ("52-week Low", fmt_num(q.get("year_low"))),
            ("P/E (TTM)", fmt_num(m.get("pe_ratio"))),
            ("Forward P/E", fmt_num(m.get("forward_pe"))),
            ("Dividend Yield", fmt_pct((m.get("dividend_yield") or 0) * 100, signed=False)
             if m.get("dividend_yield") is not None else "-"),
            ("Price / Book", fmt_num(m.get("price_to_book"))),
            ("Profit Margin", fmt_pct((m.get("profit_margin") or 0) * 100, signed=False)
             if m.get("profit_margin") is not None else "-"),
            ("Return on Equity", fmt_pct((m.get("return_on_equity") or 0) * 100, signed=False)
             if m.get("return_on_equity") is not None else "-"),
        ])


def price_chart_widget(symbol: str, key: str = "eq"):
    periods = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "5Y": 60}
    with st.container(border=True):
        widget_header("Price Chart", symbol)
        plabel = st.radio("Period", list(periods.keys()), index=3,
                          horizontal=True, key=f"{key}_period",
                          label_visibility="collapsed")
        try:
            hist = get_history(symbol, periods[plabel])
        except Exception:
            st.warning("Chart data unavailable right now.")
            return
        if hist.empty:
            st.warning("No historical data returned.")
            return
        st.plotly_chart(candlestick_chart(hist, symbol, 430),
                        width="stretch", config={"displayModeBar": False})


def fundamentals_widget(symbol: str):
    with st.container(border=True):
        widget_header("Financials", symbol)
        tabs = st.tabs(["Income Statement", "Balance Sheet", "Cash Flow"])
        for tab, (kind, items) in zip(tabs, [
            ("income", INCOME_ITEMS), ("balance", BALANCE_ITEMS), ("cash", CASH_ITEMS)]):
            with tab:
                try:
                    df = get_statement(symbol, kind)
                    tbl = stmt_table(df, items)
                    if tbl.empty:
                        st.info("No rows returned for this statement.")
                    else:
                        st.dataframe(tbl, width="stretch")
                except Exception:
                    st.warning("Statement unavailable right now.")


def profile_widget(symbol: str):
    with st.container(border=True):
        widget_header("Company Profile", symbol)
        try:
            p = get_profile(symbol)
        except Exception:
            st.warning("Profile unavailable right now.")
            return
        desc = p.get("long_description") or ""
        st.markdown(
            f"<div class='ws-quote-name'>{p.get('name', symbol)}</div>"
            f"<div class='ws-quote-sub'>{p.get('sector') or ''}"
            f"{' · ' + str(p.get('industry')) if p.get('industry') else ''}"
            f"{' · ' + fmt_big(p.get('employees')) + ' employees' if p.get('employees') else ''}"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='ws-news-sum' style='margin-top:8px'>{desc[:900]}"
            f"{'…' if len(desc) > 900 else ''}</div>",
            unsafe_allow_html=True,
        )
        if p.get("company_url"):
            st.markdown(f"[{p['company_url']}]({p['company_url']})")


def news_widget(symbol: str, limit: int = 8):
    with st.container(border=True):
        widget_header("News", symbol)
        try:
            news = get_news(symbol, limit)
        except Exception:
            st.info("No news available right now.")
            return
        for _, row in news.iterrows():
            ts = row.get("date")
            when = ts.strftime("%b %d, %Y %H:%M UTC") if hasattr(ts, "strftime") else ""
            src = row.get("source") or ""
            summary = (row.get("summary") or "")[:220]
            st.markdown(
                f"<div style='padding:6px 0;border-bottom:1px solid {C['border_soft']}'>"
                f"<a class='ws-news-title' href='{row['url']}' target='_blank'>{row['title']}</a>"
                f"<div class='ws-news-meta'>{src}{' · ' if src and when else ''}{when}</div>"
                f"<div class='ws-news-sum'>{summary}</div></div>",
                unsafe_allow_html=True,
            )


if dashboard == "Equity Dashboard":
    quote_header(SYMBOL)
    left, right = st.columns([1, 2])
    with left:
        key_metrics_widget(SYMBOL)
    with right:
        price_chart_widget(SYMBOL)
    l2, r2 = st.columns([3, 2])
    with l2:
        fundamentals_widget(SYMBOL)
    with r2:
        profile_widget(SYMBOL)
    news_widget(SYMBOL)

elif dashboard == "Charting":
    with st.container(border=True):
        widget_header("Advanced Chart", SYMBOL)
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1:
            iv = st.radio("Interval", ["1D (1m)", "1W (1h)", "1M", "3M", "6M", "1Y", "5Y"],
                          index=5, horizontal=True, key="ch_interval")
        with c3:
            show_ma = st.toggle("Moving averages (50/200)", value=True)
        try:
            if iv == "1D (1m)":
                hist = get_intraday(SYMBOL, days=2, interval="1m")
            elif iv == "1W (1h)":
                hist = get_intraday(SYMBOL, days=7, interval="1h")
            else:
                months = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "5Y": 60}[iv]
                hist = get_history(SYMBOL, months)
        except Exception:
            st.warning("Chart data unavailable right now.")
            hist = pd.DataFrame()
        if hist.empty:
            st.warning("No data returned for this interval.")
        else:
            st.plotly_chart(
                candlestick_chart(hist, SYMBOL, 620, show_ma=show_ma and "1" in iv and iv != "1D (1m)"),
                width="stretch", config={"displayModeBar": False})

elif dashboard == "News":
    news_widget(SYMBOL, limit=12)
    with st.container(border=True):
        widget_header("Watchlist Headlines")
        for sym in st.session_state.watchlist[:4]:
            try:
                news = get_news(sym, 3)
            except Exception:
                continue
            st.markdown(f"**{sym}**")
            for _, row in news.iterrows():
                st.markdown(
                    f"- <a href='{row['url']}' target='_blank'>{row['title']}</a>",
                    unsafe_allow_html=True)

elif dashboard == "World Economics":
    INDICES = [
        ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq Composite"), ("^DJI", "Dow Jones"),
        ("^RUT", "Russell 2000"), ("^VIX", "VIX"), ("^FTSE", "FTSE 100"),
        ("^N225", "Nikkei 225"), ("^GDAXI", "DAX"),
    ]
    MACRO = [
        ("GC=F", "Gold"), ("SI=F", "Silver"), ("CL=F", "WTI Crude"),
        ("BTC-USD", "Bitcoin"), ("ETH-USD", "Ethereum"), ("EURUSD=X", "EUR/USD"),
    ]

    def macro_table(items, title):
        with st.container(border=True):
            widget_header(title)
            rows = []
            for sym, name in items:
                try:
                    q = get_quote(sym)
                    last, chg, pct = quote_change(q)
                    rows.append({
                        "Symbol": sym, "Name": q.get("name") or name,
                        "Last": fmt_num(last),
                        "Chg": f"{chg:+,.2f}" if chg is not None else "-",
                        "Chg %": f"{pct:+.2f}%" if pct is not None else "-",
                        "Volume": fmt_big(q.get("volume")),
                    })
                except Exception:
                    rows.append({"Symbol": sym, "Name": name, "Last": "-",
                                 "Chg": "-", "Chg %": "-", "Volume": "-"})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    macro_table(INDICES, "Major Indices")
    macro_table(MACRO, "Commodities · Crypto · FX")
    with st.container(border=True):
        widget_header("Index Chart")
        pick = st.selectbox("Instrument", [s for s, _ in INDICES + MACRO],
                            format_func=lambda s: dict(INDICES + MACRO).get(s, s))
        try:
            hist = get_history(pick, 12)
            st.plotly_chart(candlestick_chart(hist, pick, 480),
                            width="stretch", config={"displayModeBar": False})
        except Exception:
            st.warning("Chart data unavailable right now.")

elif dashboard == "Screener":
    with st.container(border=True):
        widget_header("Market Movers", "US equities")
        tabs = st.tabs(["Top Gainers", "Top Losers", "Most Active"])
        for tab, kind in zip(tabs, ["gainers", "losers", "active"]):
            with tab:
                try:
                    df = get_movers(kind, 50)
                    show = pd.DataFrame({
                        "Symbol": df["symbol"],
                        "Name": df["name"],
                        "Price": df["price"].map(lambda v: fmt_num(v)),
                        "Chg": df["change"].map(lambda v: f"{v:+,.2f}"),
                        "Chg %": df["percent_change"].map(lambda v: f"{float(v):+.2f}%"),
                        "Volume": df["volume"].map(fmt_big),
                        "MA 50": df["ma50"].map(lambda v: fmt_num(v)),
                        "MA 200": df["ma200"].map(lambda v: fmt_num(v)),
                    })
                    st.dataframe(show, hide_index=True, width="stretch", height=520)
                except Exception:
                    st.warning("Screener data unavailable right now.")
        jump = st.selectbox("Open in Equity Dashboard",
                            [""] + sorted(get_movers("gainers", 50)["symbol"].tolist()
                                          if True else []), key="scr_jump")
        if jump:
            st.session_state.symbol = jump
            st.rerun()

elif dashboard == "Watchlist":
    with st.container(border=True):
        widget_header("Watchlist", "editable")
        wl_text = st.text_input("Symbols (comma-separated)",
                                ", ".join(st.session_state.watchlist))
        new_wl = [s.strip().upper() for s in wl_text.split(",") if s.strip()]
        if new_wl != st.session_state.watchlist:
            st.session_state.watchlist = new_wl
        rows = []
        for sym in st.session_state.watchlist:
            try:
                q = get_quote(sym)
                last, chg, pct = quote_change(q)
                rows.append({
                    "Symbol": sym, "Name": q.get("name") or sym,
                    "Last": fmt_num(last),
                    "Chg": f"{chg:+,.2f}" if chg is not None else "-",
                    "Chg %": f"{pct:+.2f}%" if pct is not None else "-",
                    "Volume": fmt_big(q.get("volume")),
                    "MA 50": fmt_num(q.get("ma_50d")),
                    "MA 200": fmt_num(q.get("ma_200d")),
                })
            except Exception:
                rows.append({"Symbol": sym, "Name": sym, "Last": "-", "Chg": "-",
                             "Chg %": "-", "Volume": "-", "MA 50": "-", "MA 200": "-"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        jump2 = st.selectbox("Open in Equity Dashboard", [""] + st.session_state.watchlist,
                             key="wl_jump")
        if jump2:
            st.session_state.symbol = jump2
            st.rerun()
    for sym in st.session_state.watchlist[:3]:
        with st.container(border=True):
            widget_header("Price Chart", sym)
            try:
                hist = get_history(sym, 6)
                st.plotly_chart(candlestick_chart(hist, sym, 320),
                                width="stretch", config={"displayModeBar": False})
            except Exception:
                st.warning("Chart unavailable.")
