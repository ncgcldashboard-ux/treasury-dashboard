import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(layout="wide")

st.title("NCGCL Fixed Income Dashboard")

# ---------------------------
# Upload
# ---------------------------
file = st.file_uploader("Upload Portfolio CSV", type=["csv"])

if file is None:
    st.info("Upload your Google Sheets CSV export to proceed.")
    st.stop()

df = pd.read_csv(file)

# ---------------------------
# Clean columns
# ---------------------------
def clean(x):
    try:
        return float(str(x).replace(",", "").replace("%", ""))
    except:
        return np.nan

df.columns = [c.strip() for c in df.columns]

# Remove summary rows
df = df[~df["Instrument"].isin(["Total", "Borrowing", "NAV", "NAV Units"])]

# Convert numeric fields
cols = [
    "Cost of Placement", "Past Week", "Current Week",
    "Gain/Loss", "Rate", "Modified Duration",
    "PVBP", "Convexity"
]

for c in cols:
    if c in df.columns:
        df[c] = df[c].apply(clean)

# ---------------------------
# Core Metrics
# ---------------------------
total_mv = df["Current Week"].sum()
total_pnl = df["Gain/Loss"].sum()
total_pvbp = df["PVBP"].sum()

duration = (df["Modified Duration"] * df["Current Week"]).sum() / total_mv
convexity = (df["Convexity"] * df["Current Week"]).sum() / total_mv

# ---------------------------
# KPI Display
# ---------------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric("AUM", f"{total_mv:,.0f}")
col2.metric("Weekly P&L", f"{total_pnl:,.0f}")
col3.metric("Duration", f"{duration:.2f}")
col4.metric("PVBP", f"{total_pvbp:,.0f}")

st.markdown("---")

# ---------------------------
# Holdings Table
# ---------------------------
st.subheader("Holdings")

st.dataframe(df, use_container_width=True)

# ---------------------------
# P&L Attribution
# ---------------------------
st.subheader("P&L Attribution")

fig1 = px.bar(
    df,
    x="Instrument",
    y="Gain/Loss",
    color="Gain/Loss",
    color_continuous_scale=["red", "green"]
)
st.plotly_chart(fig1, use_container_width=True)

# ---------------------------
# Yield vs Duration
# ---------------------------
st.subheader("Yield vs Duration")

fig2 = px.scatter(
    df,
    x="Modified Duration",
    y="Rate",
    size="Current Week",
    text="Instrument"
)

st.plotly_chart(fig2, use_container_width=True)

# ---------------------------
# Stress Testing
# ---------------------------
st.subheader("Stress Testing (Parallel Shift)")

shocks = [-100, -50, -25, 25, 50, 100]

stress_results = []

for shock in shocks:
    dy = shock / 10000
    pnl = np.sum(
        (-df["Modified Duration"] * dy +
         0.5 * df["Convexity"] * dy**2) * df["Current Week"]
    )
    stress_results.append({"Shock (bps)": shock, "P&L": pnl})

stress_df = pd.DataFrame(stress_results)

fig3 = px.bar(stress_df, x="Shock (bps)", y="P&L")
st.plotly_chart(fig3, use_container_width=True)

st.dataframe(stress_df)

# ---------------------------
# Portfolio Analytics
# ---------------------------
st.subheader("Portfolio Analytics")

colA, colB = st.columns(2)

with colA:
    st.metric("Weighted Yield", f"{(df['Rate'] * df['Current Week']).sum()/total_mv:.2f}%")

with colB:
    st.metric("Convexity", f"{convexity:.4f}")
