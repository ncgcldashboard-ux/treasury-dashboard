import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="WoW Positions Dashboard",
    page_icon="📈",
    layout="wide",
)

# ── Data loading ──────────────────────────────────────────────────────────────
SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRT3RtrWFf_TOzCazJ6zyYSnmfuCaUcCImmKZMEEOt4hwZP3bql9Jg49VnBuTvb9Gi31nxKNjTnQ2ha"
    "/pub?gid=131765111&single=true&output=csv"
)

@st.cache_data(ttl=300)
def load_data(url: str) -> pd.DataFrame:
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()
    # Try to parse any column that looks like a date
    for col in df.columns:
        if df[col].dtype == object:
            try:
                parsed = pd.to_datetime(df[col], infer_datetime_format=True)
                if parsed.notna().sum() > len(df) * 0.5:
                    df[col] = parsed
            except Exception:
                pass
    return df

# ── Load ──────────────────────────────────────────────────────────────────────
try:
    df = load_data(SHEET_CSV_URL)
except Exception as e:
    st.error(f"❌ Could not load data: {e}")
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📊 WoW Positions Dashboard")
st.caption("Data sourced live from Google Sheets · refreshes every 5 minutes")
st.divider()

# ── Sidebar – filters & column mapping ───────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    st.subheader("Column Mapping")

    all_cols = df.columns.tolist()

    # Auto-detect likely columns
    def guess(keywords, cols):
        for kw in keywords:
            for c in cols:
                if kw.lower() in c.lower():
                    return c
        return cols[0]

    keyword_col = st.selectbox(
        "Keyword / Item column",
        all_cols,
        index=all_cols.index(guess(["keyword", "query", "term", "page", "url", "item"], all_cols)),
    )

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()

    if numeric_cols:
        position_col = st.selectbox(
            "Current Position column",
            numeric_cols,
            index=numeric_cols.index(
                guess(["position", "rank", "pos", "current"], numeric_cols)
            ) if guess(["position", "rank", "pos", "current"], numeric_cols) in numeric_cols else 0,
        )
        prev_position_col = st.selectbox(
            "Previous Position column (optional)",
            ["— None —"] + numeric_cols,
            index=0,
        )
        prev_position_col = None if prev_position_col == "— None —" else prev_position_col
    else:
        st.warning("No numeric columns detected for positions.")
        st.stop()

    # Optional filters
    st.subheader("Filters")
    cat_cols = [c for c in df.select_dtypes(include="object").columns if c != keyword_col]
    active_filters = {}
    for col in cat_cols[:3]:  # show up to 3 categorical filter dropdowns
        unique_vals = sorted(df[col].dropna().unique().tolist())
        if 1 < len(unique_vals) <= 50:
            chosen = st.multiselect(f"{col}", unique_vals, default=unique_vals)
            active_filters[col] = chosen

    if numeric_cols:
        pos_min = int(df[position_col].min())
        pos_max = int(df[position_col].max())
        pos_range = st.slider(
            f"{position_col} range",
            pos_min, pos_max, (pos_min, pos_max),
        )

# ── Apply filters ─────────────────────────────────────────────────────────────
filtered = df.copy()
for col, vals in active_filters.items():
    filtered = filtered[filtered[col].isin(vals)]
filtered = filtered[
    (filtered[position_col] >= pos_range[0]) &
    (filtered[position_col] <= pos_range[1])
]

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)

avg_pos = filtered[position_col].mean()
median_pos = filtered[position_col].median()
top10 = (filtered[position_col] <= 10).sum()
total = len(filtered)

k1.metric("Total Keywords", f"{total:,}")
k2.metric("Avg Position", f"{avg_pos:.1f}")
k3.metric("Median Position", f"{median_pos:.1f}")
k4.metric("Top-10 Keywords", f"{top10:,}", f"{top10/total*100:.1f}% of total" if total else "")

if prev_position_col:
    filtered["_delta"] = filtered[prev_position_col] - filtered[position_col]  # positive = improved
    avg_delta = filtered["_delta"].mean()
    improved = (filtered["_delta"] > 0).sum()
    declined = (filtered["_delta"] < 0).sum()
    unchanged = (filtered["_delta"] == 0).sum()

    st.divider()
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Avg Position Change", f"{avg_delta:+.1f}", help="Positive = improved ranking")
    d2.metric("Improved ↑", f"{improved:,}")
    d3.metric("Declined ↓", f"{declined:,}")
    d4.metric("Unchanged →", f"{unchanged:,}")

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

# 1. Position distribution histogram
with col_left:
    st.subheader("Position Distribution")
    fig_hist = px.histogram(
        filtered,
        x=position_col,
        nbins=20,
        color_discrete_sequence=["#636EFA"],
        labels={position_col: "Position"},
        template="plotly_white",
    )
    fig_hist.update_layout(bargap=0.05, margin=dict(t=20, b=20))
    st.plotly_chart(fig_hist, use_container_width=True)

# 2. WoW change scatter (if prev column exists)
with col_right:
    if prev_position_col:
        st.subheader("Current vs Previous Position")
        fig_scatter = px.scatter(
            filtered,
            x=prev_position_col,
            y=position_col,
            hover_name=keyword_col,
            color="_delta",
            color_continuous_scale="RdYlGn",
            color_continuous_midpoint=0,
            labels={
                prev_position_col: "Previous Position",
                position_col: "Current Position",
                "_delta": "Improvement",
            },
            template="plotly_white",
        )
        # diagonal reference line
        lim = max(filtered[prev_position_col].max(), filtered[position_col].max())
        fig_scatter.add_shape(
            type="line", x0=1, y0=1, x1=lim, y1=lim,
            line=dict(color="grey", dash="dash"),
        )
        fig_scatter.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig_scatter, use_container_width=True)
    else:
        st.subheader("Top 20 Keywords by Position")
        top20 = filtered.nsmallest(20, position_col)[[keyword_col, position_col]]
        fig_bar = px.bar(
            top20,
            x=position_col,
            y=keyword_col,
            orientation="h",
            color=position_col,
            color_continuous_scale="Blues_r",
            template="plotly_white",
            labels={position_col: "Position", keyword_col: "Keyword"},
        )
        fig_bar.update_layout(yaxis=dict(autorange="reversed"), margin=dict(t=20, b=20))
        st.plotly_chart(fig_bar, use_container_width=True)

# 3. Position buckets pie
st.subheader("Position Buckets")
buckets = pd.cut(
    filtered[position_col],
    bins=[0, 3, 10, 20, 50, float("inf")],
    labels=["Top 3", "4–10", "11–20", "21–50", "50+"],
)
bucket_counts = buckets.value_counts().sort_index()
col_pie, col_bucket_bar = st.columns(2)

with col_pie:
    fig_pie = px.pie(
        values=bucket_counts.values,
        names=bucket_counts.index,
        color_discrete_sequence=px.colors.sequential.Blues_r,
        template="plotly_white",
        hole=0.4,
    )
    fig_pie.update_layout(margin=dict(t=10, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)

with col_bucket_bar:
    fig_bbar = px.bar(
        x=bucket_counts.index,
        y=bucket_counts.values,
        color=bucket_counts.index,
        color_discrete_sequence=px.colors.sequential.Blues_r,
        labels={"x": "Bucket", "y": "Count"},
        template="plotly_white",
    )
    fig_bbar.update_layout(showlegend=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig_bbar, use_container_width=True)

# 4. WoW movers table
if prev_position_col:
    st.subheader("🏆 Top Movers & Losers")
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**📈 Biggest Improvers**")
        top_movers = (
            filtered[[keyword_col, prev_position_col, position_col, "_delta"]]
            .sort_values("_delta", ascending=False)
            .head(10)
            .rename(columns={"_delta": "Δ Position"})
            .reset_index(drop=True)
        )
        top_movers.index += 1
        st.dataframe(top_movers, use_container_width=True)
    with m2:
        st.markdown("**📉 Biggest Declines**")
        top_losers = (
            filtered[[keyword_col, prev_position_col, position_col, "_delta"]]
            .sort_values("_delta", ascending=True)
            .head(10)
            .rename(columns={"_delta": "Δ Position"})
            .reset_index(drop=True)
        )
        top_losers.index += 1
        st.dataframe(top_losers, use_container_width=True)

# 5. Raw data expander
with st.expander("🗂 View Raw Data"):
    st.dataframe(filtered.reset_index(drop=True), use_container_width=True, height=400)
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download filtered data as CSV", csv, "wow_positions.csv", "text/csv")
