"""
NCGCL Investment Dashboard
--------------------------
Reads live data from the NCGCL Google Sheet (PKRV Rates, Dashboard, SPI Time Series tabs)
and renders a Goldman-Sachs-styled (navy / grey / white) Streamlit dashboard.

SETUP
-----
1. pip install streamlit pandas plotly requests
2. Sheet must be shared as "Anyone with the link can view" for the CSV export
   endpoint to work without auth. If it's private, see the gspread note at the
   bottom of this file.
3. Run:  streamlit run app.py

The sheet ID is hardcoded below. Tab names are pulled via the gviz CSV export,
which works per-tab by name (spaces must be URL-encoded).
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from urllib.parse import quote
import requests
from io import StringIO

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
SHEET_ID = "1_meE64ybCxhVbiJxDwyjBY1VP9NWIdpukLM05xhCc10"

TABS = {
    "pkrv": "PKRV Rates",
    "portfolio": "Dashboard",
    "spi": "SPI Time Series",
}

NAVY = "#035076"
GREY = "#BABABA"
NAVY_LIGHT = "#5B8AA6"
INK = "#1a1a1a"

st.set_page_config(page_title="NCGCL Investment Dashboard", layout="wide")

# ----------------------------------------------------------------------------
# STYLING — Goldman-style: white background, navy/grey palette, tight chrome
# ----------------------------------------------------------------------------
st.markdown(f"""
<style>
    .stApp {{ background-color: #ffffff; }}
    h1, h2, h3 {{ color: {NAVY}; font-family: Helvetica, Arial, sans-serif; }}
    .kicker {{
        color: {NAVY}; font-size: 11px; font-weight: 700;
        letter-spacing: 1.5px; text-transform: uppercase;
    }}
    .block-container {{ padding-top: 2rem; }}
    div[data-testid="stMetricValue"] {{ color: {NAVY}; font-weight: 700; }}
    div[data-testid="stMetric"] {{
        background-color: #fafafa; border: 1px solid #e6e6e6;
        border-radius: 3px; padding: 10px 14px;
    }}
    hr {{ border-top: 2px solid {NAVY}; }}
</style>
""", unsafe_allow_html=True)

PLOTLY_TEMPLATE = dict(
    layout=go.Layout(
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(family="Helvetica, Arial, sans-serif", color=INK, size=12),
        colorway=[NAVY, GREY, NAVY_LIGHT, "#7A97A6", "#D8D8D8"],
        xaxis=dict(showgrid=False, linecolor="#dddddd"),
        yaxis=dict(showgrid=True, gridcolor="#eeeeee", zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=40, l=10, r=10, b=10),
    )
)

# ----------------------------------------------------------------------------
# DATA LOADING
# ----------------------------------------------------------------------------
@st.cache_data(ttl=120)
def load_tab(sheet_id: str, tab_name: str) -> pd.DataFrame:
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq"
        f"?tqx=out:csv&sheet={quote(tab_name)}"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    df = df.dropna(how="all").dropna(axis=1, how="all")
    return df

def try_load(tab_name: str, label: str):
    try:
        return load_tab(SHEET_ID, tab_name), None
    except Exception as e:
        return None, str(e)

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------
st.markdown('<div class="kicker">NCGCL &middot; Treasury &middot; Live Dashboard</div>', unsafe_allow_html=True)
st.title("Investment Dashboard")
st.markdown("---")

with st.sidebar:
    st.markdown(f"<h3 style='color:{NAVY}'>Controls</h3>", unsafe_allow_html=True)
    if st.button("🔄 Refresh data now"):
        st.cache_data.clear()
    st.caption("Data auto-refreshes every 2 minutes. Sheet must be shared as 'Anyone with link can view'.")

tab1, tab2, tab3 = st.tabs(["📈 PKRV Curve", "💼 Portfolio", "📊 SPI Time Series"])

# ----------------------------------------------------------------------------
# TAB 1: PKRV RATES
# ----------------------------------------------------------------------------
with tab1:
    df_pkrv, err = try_load(TABS["pkrv"], "PKRV")
    if err:
        st.error(f"Couldn't load '{TABS['pkrv']}' tab: {err}")
        st.info("Confirm the sheet is shared as 'Anyone with the link can view', and that the tab name matches exactly.")
    else:
        st.subheader("PKRV Rates")
        # Expect first column = Tenor, remaining columns = dates
        date_cols = [c for c in df_pkrv.columns if c != df_pkrv.columns[0]]
        tenor_col = df_pkrv.columns[0]

        c1, c2 = st.columns([1, 1])
        with c1:
            selected_dates = st.multiselect(
                "Compare dates", options=date_cols,
                default=date_cols[-3:] if len(date_cols) >= 3 else date_cols,
            )
        with c2:
            tenor_for_series = st.selectbox(
                "Tenor for time-series view",
                options=df_pkrv[tenor_col].dropna().unique().tolist(),
                index=0,
            )

        # Curve chart: tenor on x-axis, selected dates as lines
        if selected_dates:
            fig = go.Figure()
            colors = [NAVY, NAVY_LIGHT, GREY, "#7A97A6", "#D8D8D8"]
            for i, d in enumerate(selected_dates):
                fig.add_trace(go.Scatter(
                    x=df_pkrv[tenor_col],
                    y=pd.to_numeric(df_pkrv[d], errors="coerce"),
                    mode="lines+markers",
                    name=str(d),
                    line=dict(width=3 if i == len(selected_dates) - 1 else 2,
                              color=colors[i % len(colors)]),
                ))
            fig.update_layout(**PLOTLY_TEMPLATE["layout"],
                               title="PKRV Curve by Tenor",
                               yaxis_title="Yield (%)")
            st.plotly_chart(fig, use_container_width=True)

        # Time series for one tenor across all dates
        row = df_pkrv[df_pkrv[tenor_col] == tenor_for_series]
        if not row.empty:
            series = row[date_cols].T
            series.columns = ["yield"]
            series["yield"] = pd.to_numeric(series["yield"], errors="coerce")
            series.index.name = "date"
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=series.index, y=series["yield"], mode="lines",
                line=dict(color=NAVY, width=3), name=str(tenor_for_series),
            ))
            fig2.update_layout(**PLOTLY_TEMPLATE["layout"],
                                title=f"{tenor_for_series} PKRV Over Time",
                                yaxis_title="Yield (%)")
            st.plotly_chart(fig2, use_container_width=True)

        with st.expander("Raw PKRV data"):
            st.dataframe(df_pkrv, use_container_width=True)

# ----------------------------------------------------------------------------
# TAB 2: PORTFOLIO (Dashboard tab)
# ----------------------------------------------------------------------------
with tab2:
    df_port, err = try_load(TABS["portfolio"], "Portfolio")
    if err:
        st.error(f"Couldn't load '{TABS['portfolio']}' tab: {err}")
        st.info("Confirm the sheet is shared as 'Anyone with the link can view', and that the tab name matches exactly.")
    else:
        st.subheader("Portfolio — Dashboard")

        # Try to auto-detect numeric columns for KPI cards
        numeric_cols = df_port.select_dtypes(include="number").columns.tolist()
        if numeric_cols:
            kpi_cols = st.columns(min(4, len(numeric_cols)))
            for i, col in enumerate(numeric_cols[:4]):
                with kpi_cols[i]:
                    st.metric(col, f"{df_port[col].sum():,.0f}")

        # Instrument / Contribution style breakdown, if present
        lower_cols = {c.lower(): c for c in df_port.columns}
        if "instrument" in lower_cols and "contribution" in lower_cols:
            inst_col = lower_cols["instrument"]
            contrib_col = lower_cols["contribution"]
            sub = df_port[[inst_col, contrib_col]].dropna()
            sub[contrib_col] = pd.to_numeric(sub[contrib_col], errors="coerce")
            sub = sub.dropna()

            c1, c2 = st.columns(2)
            with c1:
                fig = px.bar(
                    sub.sort_values(contrib_col, ascending=True),
                    x=contrib_col, y=inst_col, orientation="h",
                    color_discrete_sequence=[NAVY],
                )
                fig.update_layout(**PLOTLY_TEMPLATE["layout"], title="Contribution by Instrument")
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                fig2 = px.pie(
                    sub, names=inst_col, values=contrib_col, hole=0.55,
                    color_discrete_sequence=[NAVY, NAVY_LIGHT, GREY, "#7A97A6", "#D8D8D8", "#0A6C99"],
                )
                fig2.update_layout(**PLOTLY_TEMPLATE["layout"], title="Allocation Mix")
                st.plotly_chart(fig2, use_container_width=True)

        st.markdown("#### Full table")
        st.dataframe(df_port, use_container_width=True)

# ----------------------------------------------------------------------------
# TAB 3: SPI TIME SERIES
# ----------------------------------------------------------------------------
with tab3:
    df_spi, err = try_load(TABS["spi"], "SPI")
    if err:
        st.error(f"Couldn't load '{TABS['spi']}' tab: {err}")
        st.info("Confirm the sheet is shared as 'Anyone with the link can view', and that the tab name matches exactly.")
    else:
        st.subheader("SPI Time Series")

        # Guess a date column and a value column
        cols = df_spi.columns.tolist()
        date_guess = next((c for c in cols if "date" in c.lower()), cols[0])
        val_candidates = [c for c in cols if c != date_guess]

        c1, c2 = st.columns([1, 2])
        with c1:
            date_col = st.selectbox("Date column", options=cols, index=cols.index(date_guess))
        with c2:
            value_cols = st.multiselect(
                "Series to plot", options=val_candidates,
                default=val_candidates[:1] if val_candidates else [],
            )

        if value_cols:
            plot_df = df_spi[[date_col] + value_cols].copy()
            plot_df[date_col] = pd.to_datetime(plot_df[date_col], errors="coerce")
            for vc in value_cols:
                plot_df[vc] = pd.to_numeric(plot_df[vc], errors="coerce")
            plot_df = plot_df.dropna(subset=[date_col])

            fig = go.Figure()
            colors = [NAVY, GREY, NAVY_LIGHT, "#7A97A6", "#D8D8D8"]
            for i, vc in enumerate(value_cols):
                fig.add_trace(go.Scatter(
                    x=plot_df[date_col], y=plot_df[vc], mode="lines",
                    name=vc, line=dict(color=colors[i % len(colors)], width=2.5),
                ))
            fig.update_layout(**PLOTLY_TEMPLATE["layout"], title="SPI Time Series")
            st.plotly_chart(fig, use_container_width=True)

        with st.expander("Raw SPI data"):
            st.dataframe(df_spi, use_container_width=True)

# ----------------------------------------------------------------------------
# NOTES
# ----------------------------------------------------------------------------
# If the sheet is private (not "anyone with link can view"), swap the loader
# for gspread + a service account:
#
#   import gspread
#   gc = gspread.service_account(filename="creds.json")
#   sh = gc.open_by_key(SHEET_ID)
#   df = pd.DataFrame(sh.worksheet(tab_name).get_all_records())
#
# and share the sheet with the service account's client_email.
