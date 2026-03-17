import re
import math
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="NCGCL Fixed Income Dashboard",
    page_icon="📊",
    layout="wide",
)

SHEET_ID = "1_meE64ybCxhVbiJxDwyjBY1VP9NWIdpukLM05xhCc10"
DEFAULT_GID = "0"  # first worksheet; change if needed

BRAND = {
    "primary": "#035076",
    "accent": "#39A949",
    "dark": "#021E2E",
    "surface": "#F4F7FA",
    "border": "#D0DBE6",
    "text": "#1A2B38",
    "muted": "#5C7A8C",
    "danger": "#D92D20",
    "warning": "#F59E0B",
}

st.markdown(
    f"""
    <style>
        .block-container {{
            max-width: 1450px;
            padding-top: 1rem;
            padding-bottom: 2rem;
        }}
        .metric-card {{
            background: white;
            border: 1px solid {BRAND["border"]};
            border-top: 4px solid {BRAND["primary"]};
            border-radius: 8px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.6rem;
        }}
        .metric-label {{
            font-size: 0.72rem;
            color: {BRAND["muted"]};
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }}
        .metric-value {{
            font-size: 1.7rem;
            font-weight: 800;
            color: {BRAND["primary"]};
            line-height: 1.1;
            margin-top: 0.2rem;
        }}
        .metric-sub {{
            font-size: 0.8rem;
            color: {BRAND["muted"]};
            margin-top: 0.25rem;
        }}
        .page-header {{
            background: linear-gradient(135deg, {BRAND["dark"]} 0%, {BRAND["primary"]} 100%);
            border-radius: 10px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 1.2rem;
            color: white;
        }}
        .section-title {{
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: {BRAND["primary"]};
            font-weight: 800;
            margin: 1rem 0 0.75rem 0;
            padding-bottom: 0.35rem;
            border-bottom: 2px solid {BRAND["border"]};
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
def fmt_pkr(x: float) -> str:
    if pd.isna(x):
        return "-"
    if abs(x) >= 1e9:
        return f"PKR {x/1e9:,.2f}B"
    if abs(x) >= 1e6:
        return f"PKR {x/1e6:,.2f}M"
    return f"PKR {x:,.0f}"

def fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "-"
    return f"{x:.2f}%"

def to_float(val):
    if pd.isna(val):
        return math.nan
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if s == "":
        return math.nan
    s = s.replace(",", "").replace("%", "").replace("*", "")
    s = re.sub(r"[^\d\.\-]", "", s)
    if s in {"", "-", ".", "-."}:
        return math.nan
    try:
        return float(s)
    except Exception:
        return math.nan

def standardize_columns(cols):
    return [re.sub(r"\s+", " ", str(c)).strip() for c in cols]

@st.cache_data(ttl=300)
def load_sheet_csv(sheet_id: str, gid: str) -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(pd.io.common.StringIO(r.text))
    df.columns = standardize_columns(df.columns)
    return df

def clean_portfolio_df(raw_df: pd.DataFrame):
    df = raw_df.copy()
    df.columns = standardize_columns(df.columns)

    expected_map = {
        "Instrument": "instrument",
        "Cost of Placement": "cost",
        "Past Week": "past_week",
        "Current Week": "current_week",
        "Gain/Loss": "gain_loss",
        "1 Day Returns": "ret_1d",
        "15 Day Returns": "ret_15d",
        "30 Day Returns": "ret_30d",
        "90 Day Returns": "ret_90d",
        "7 Day NAV": "nav_7d",
        "NAVs": "nav_latest",
        "Number of Units": "units",
        "Date of Placement": "placement_date",
        "Date of Maturity": "maturity_date",
        "Weekly Yield": "weekly_yield",
        "Rate": "rate",
        "Days to Maturity": "days_to_maturity",
        "Remaining Days": "remaining_days",
        "Concentration (%)": "concentration",
        "PVBP": "pvbp",
        "Modified Duration": "mod_duration",
        "Convexity": "convexity",
    }

    renamed = {}
    for col in df.columns:
        if col in expected_map:
            renamed[col] = expected_map[col]
    df = df.rename(columns=renamed)

    numeric_cols = [
        "cost", "past_week", "current_week", "gain_loss",
        "ret_1d", "ret_15d", "ret_30d", "ret_90d",
        "nav_7d", "nav_latest", "units",
        "weekly_yield", "rate", "days_to_maturity",
        "remaining_days", "concentration", "pvbp",
        "mod_duration", "convexity"
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = df[c].apply(to_float)

    if "placement_date" in df.columns:
        df["placement_date"] = pd.to_datetime(df["placement_date"], errors="coerce")
    if "maturity_date" in df.columns:
        df["maturity_date"] = pd.to_datetime(df["maturity_date"], errors="coerce")

    if "instrument" in df.columns:
        df["instrument"] = df["instrument"].astype(str).str.strip()

    # Keep holdings only: remove totals, borrowing, nav rows from the main holdings grid
    if "instrument" in df.columns:
        holdings = df[
            ~df["instrument"].str.lower().isin(["total", "borrowing", "nav", "nav units"])
        ].copy()
    else:
        holdings = df.copy()

    # Instrument-type classification
    def classify(name: str) -> str:
        s = str(name).lower()
        if "mtb" in s or "t-bill" in s or "treasury" in s:
            return "MTB"
        if "fund" in s or "plan" in s or "mufap" in s:
            return "Mutual Fund"
        if "sukuk" in s:
            return "Sukuk"
        if "bank" in s or "coi" in s:
            return "Placement"
        return "Other"

    if "instrument" in holdings.columns:
        holdings["asset_type"] = holdings["instrument"].apply(classify)

    return holdings, df

def extract_scalar(full_df: pd.DataFrame, label: str, value_col: str = None):
    if "instrument" not in full_df.columns:
        return math.nan
    mask = full_df["instrument"].astype(str).str.lower().eq(label.lower())
    rows = full_df[mask]
    if rows.empty:
        return math.nan
    row = rows.iloc[0]
    if value_col and value_col in row.index:
        return to_float(row[value_col])
    for c in row.index:
        v = to_float(row[c])
        if not pd.isna(v):
            return v
    return math.nan

# -----------------------------------------------------------------------------
# LOAD
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("Data Source")
    gid = st.text_input("Worksheet GID", value=DEFAULT_GID)
    refresh = st.button("Refresh data")

if refresh:
    st.cache_data.clear()

try:
    raw_df = load_sheet_csv(SHEET_ID, gid)
    holdings_df, full_df = clean_portfolio_df(raw_df)
except Exception as e:
    st.error(f"Could not load Google Sheet: {e}")
    st.stop()

# -----------------------------------------------------------------------------
# DERIVED METRICS
# -----------------------------------------------------------------------------
nav_value = extract_scalar(full_df, "NAV")
nav_units = extract_scalar(full_df, "NAV Units")
borrowing = extract_scalar(full_df, "Borrowing")

total_cost = holdings_df["cost"].sum() if "cost" in holdings_df else 0
total_prev = holdings_df["past_week"].sum() if "past_week" in holdings_df else 0
total_mv = holdings_df["current_week"].sum() if "current_week" in holdings_df else 0
total_gain = holdings_df["gain_loss"].sum() if "gain_loss" in holdings_df else 0
total_pvbp = holdings_df["pvbp"].sum() if "pvbp" in holdings_df else 0

weighted_duration = (
    (holdings_df["mod_duration"] * holdings_df["current_week"]).sum() / total_mv
    if total_mv and "mod_duration" in holdings_df else math.nan
)
weighted_convexity = (
    (holdings_df["convexity"] * holdings_df["current_week"]).sum() / total_mv
    if total_mv and "convexity" in holdings_df else math.nan
)
weighted_yield = (
    (holdings_df["rate"] * holdings_df["current_week"]).sum() / total_mv
    if total_mv and "rate" in holdings_df else math.nan
)

weekly_return = ((total_mv / total_prev) - 1) * 100 if total_prev else math.nan
gross_return_on_cost = (total_gain / total_cost) * 100 if total_cost else math.nan
net_assets = total_mv - borrowing if not pd.isna(borrowing) else total_mv

# Scenario stress
def stress_pnl(bp: int):
    dy = bp / 10000.0
    if "mod_duration" not in holdings_df or "convexity" not in holdings_df:
        return math.nan
    pnl = (
        -holdings_df["mod_duration"] * dy
        + 0.5 * holdings_df["convexity"] * (dy ** 2)
    ) * holdings_df["current_week"]
    return pnl.sum()

scenarios = pd.DataFrame({
    "Shock (bps)": [-100, -50, -25, 25, 50, 100]
})
scenarios["P&L"] = scenarios["Shock (bps)"].apply(stress_pnl)

# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="page-header">
        <h2 style="margin:0;">NCGCL Fixed Income Portfolio Dashboard</h2>
        <div style="opacity:0.85;margin-top:0.25rem;">
            Live Google Sheets-linked dashboard | Mark-to-market, NAV, PVBP, duration, convexity, stress
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

k1, k2, k3, k4, k5, k6 = st.columns(6)

cards = [
    ("Portfolio MV", fmt_pkr(total_mv), "Current week market value"),
    ("Weekly P&L", fmt_pkr(total_gain), fmt_pct(weekly_return) if not pd.isna(weekly_return) else "—"),
    ("NAV", f"{nav_value:,.2f}" if not pd.isna(nav_value) else "—", "Pulled from sheet"),
    ("Net Assets", fmt_pkr(net_assets), "After borrowing"),
    ("Portfolio PVBP", fmt_pkr(total_pvbp), "1bp parallel shift"),
    ("Mod. Duration", f"{weighted_duration:.2f}" if not pd.isna(weighted_duration) else "—", "Weighted average"),
]

for col, (label, value, sub) in zip([k1, k2, k3, k4, k5, k6], cards):
    with col:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-sub">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

k7, k8, k9, k10 = st.columns(4)
cards2 = [
    ("Weighted Yield", fmt_pct(weighted_yield), "Market-value weighted"),
    ("Weighted Convexity", f"{weighted_convexity:.4f}" if not pd.isna(weighted_convexity) else "—", "Unitless"),
    ("Borrowing", fmt_pkr(borrowing) if not pd.isna(borrowing) else "—", "Funding outstanding"),
    ("Gross Return / Cost", fmt_pct(gross_return_on_cost), "Current gain vs cost"),
]
for col, (label, value, sub) in zip([k7, k8, k9, k10], cards2):
    with col:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
                <div class="metric-sub">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

tab1, tab2, tab3, tab4 = st.tabs([
    "Holdings",
    "Composition",
    "Risk & Stress",
    "Data Quality",
])

with tab1:
    st.markdown('<div class="section-title">Holdings Detail</div>', unsafe_allow_html=True)

    display_cols = [
        c for c in [
            "instrument", "asset_type", "cost", "past_week", "current_week", "gain_loss",
            "rate", "remaining_days", "concentration", "pvbp", "mod_duration", "convexity"
        ] if c in holdings_df.columns
    ]

    show_df = holdings_df[display_cols].copy()
    rename_map = {
        "instrument": "Instrument",
        "asset_type": "Type",
        "cost": "Cost",
        "past_week": "Past Week",
        "current_week": "Current Week",
        "gain_loss": "Gain/Loss",
        "rate": "Rate (%)",
        "remaining_days": "Remaining Days",
        "concentration": "Concentration (%)",
        "pvbp": "PVBP",
        "mod_duration": "Modified Duration",
        "convexity": "Convexity",
    }
    show_df = show_df.rename(columns=rename_map)
    st.dataframe(show_df, use_container_width=True, hide_index=True)

with tab2:
    left, right = st.columns(2)

    with left:
        if {"asset_type", "current_week"}.issubset(holdings_df.columns):
            comp = holdings_df.groupby("asset_type", as_index=False)["current_week"].sum()
            fig = px.pie(
                comp,
                names="asset_type",
                values="current_week",
                hole=0.55,
                title="Portfolio Composition by Asset Type",
            )
            fig.update_layout(margin=dict(t=50, l=10, r=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    with right:
        if {"instrument", "current_week"}.issubset(holdings_df.columns):
            top = holdings_df.sort_values("current_week", ascending=True)
            fig = px.bar(
                top,
                x="current_week",
                y="instrument",
                orientation="h",
                color="asset_type" if "asset_type" in top.columns else None,
                title="Market Value by Instrument",
            )
            fig.update_layout(margin=dict(t=50, l=10, r=10, b=10), showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

    if {"instrument", "gain_loss"}.issubset(holdings_df.columns):
        fig = px.bar(
            holdings_df.sort_values("gain_loss", ascending=False),
            x="instrument",
            y="gain_loss",
            color="asset_type" if "asset_type" in holdings_df.columns else None,
            title="Weekly P&L Attribution by Instrument",
        )
        fig.update_layout(margin=dict(t=50, l=10, r=10, b=10), xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    left, right = st.columns(2)

    with left:
        if {"instrument", "pvbp"}.issubset(holdings_df.columns):
            fig = px.bar(
                holdings_df.sort_values("pvbp", ascending=False),
                x="instrument",
                y="pvbp",
                color="asset_type" if "asset_type" in holdings_df.columns else None,
                title="PVBP by Instrument",
            )
            fig.update_layout(margin=dict(t=50, l=10, r=10, b=10), xaxis_tickangle=-35)
            st.plotly_chart(fig, use_container_width=True)

    with right:
        if {"mod_duration", "rate", "current_week", "instrument"}.issubset(holdings_df.columns):
            fig = px.scatter(
                holdings_df,
                x="mod_duration",
                y="rate",
                size="current_week",
                hover_name="instrument",
                color="asset_type" if "asset_type" in holdings_df.columns else None,
                title="Yield vs Duration",
            )
            fig.update_layout(margin=dict(t=50, l=10, r=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-title">Parallel Shock Scenarios</div>', unsafe_allow_html=True)
    scen = scenarios.copy()
    scen["P&L Label"] = scen["P&L"].apply(fmt_pkr)
    fig = go.Figure(
        data=[
            go.Bar(
                x=scen["Shock (bps)"].astype(str),
                y=scen["P&L"],
                text=scen["P&L Label"],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title="Portfolio Stress P&L",
        xaxis_title="Rate Shock (bps)",
        yaxis_title="P&L (PKR)",
        margin=dict(t=50, l=10, r=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(scen[["Shock (bps)", "P&L Label"]], use_container_width=True, hide_index=True)

with tab4:
    st.markdown('<div class="section-title">Control Checks</div>', unsafe_allow_html=True)

    checks = []

    if "current_week" in holdings_df.columns:
        stale = holdings_df["current_week"].isna().sum()
        checks.append(("Missing current values", stale))

    if "pvbp" in holdings_df.columns:
        missing_pvbp = holdings_df["pvbp"].isna().sum()
        checks.append(("Missing PVBP", missing_pvbp))

    if "mod_duration" in holdings_df.columns:
        missing_dur = holdings_df["mod_duration"].isna().sum()
        checks.append(("Missing modified duration", missing_dur))

    if "convexity" in holdings_df.columns:
        missing_cx = holdings_df["convexity"].isna().sum()
        checks.append(("Missing convexity", missing_cx))

    if "concentration" in holdings_df.columns:
        over_15 = (holdings_df["concentration"] > 15).sum()
        checks.append(("Concentration > 15%", int(over_15)))

    ctrl_df = pd.DataFrame(checks, columns=["Check", "Count"])
    st.dataframe(ctrl_df, use_container_width=True, hide_index=True)

    st.caption("This app reads the Google Sheet live every 5 minutes via the export CSV endpoint.")
