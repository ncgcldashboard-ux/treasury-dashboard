import io
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup


# -----------------------------
# Streamlit config
# -----------------------------
st.set_page_config(
    page_title="NCGCL Fixed Income Dashboard",
    page_icon="📈",
    layout="wide",
)

DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1PzBGJrQ8Kd3lvsyCwoY88yeyTD8ieEKL/edit?usp=sharing&ouid=101418117469445980852&rtpof=true&sd=true"
DEFAULT_LOCAL_WORKBOOK = "/mnt/data/Transactions and Workings.xlsx"
SHEET_NAME = "WoW Positions"
DEFAULT_START_ROW = 5
DEFAULT_END_ROW = 21

MUFAP_PERF_URL = "https://www.mufap.com.pk/Industry/IndustryStatDaily?tab=1"
MUFAP_PRICING_PAGE_CANDIDATES = [
    "https://www.mufap.com.pk/Industry/IndustryStatDaily?tab=3",
    "https://www.mufap.com.pk/WebRegulations/Index?Head=Pricing&title=PKRV%2FPKISRV%2FPKFRV",
]
REQ_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"


# -----------------------------
# Utilities
# -----------------------------
def clean_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return None
    text = text.replace(",", "")
    if text.endswith("%"):
        try:
            return float(text[:-1]) / 100.0
        except ValueError:
            return None
    # handle Excel-like formula display values that already came through as strings
    try:
        return float(text)
    except ValueError:
        return None


def fmt_money(x: float) -> str:
    if pd.isna(x):
        return "-"
    x = float(x)
    if abs(x) >= 1_000_000_000:
        return f"PKR {x/1_000_000_000:.2f}bn"
    if abs(x) >= 1_000_000:
        return f"PKR {x/1_000_000:.2f}mn"
    return f"PKR {x:,.0f}"


def fmt_pct(x: float, decimals: int = 2) -> str:
    if pd.isna(x):
        return "-"
    return f"{x*100:.{decimals}f}%"


def extract_sheet_id(sheet_url: str) -> Optional[str]:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", sheet_url)
    if match:
        return match.group(1)
    return None


@dataclass
class WorkbookSource:
    name: str
    df_block: pd.DataFrame
    as_of_date: pd.Timestamp


# -----------------------------
# Workbook ingestion
# -----------------------------
@st.cache_data(ttl=60 * 15, show_spinner=False)
def read_google_sheet_block(sheet_url: str, sheet_name: str, start_row: int, end_row: int) -> WorkbookSource:
    sheet_id = extract_sheet_id(sheet_url)
    if not sheet_id:
        raise ValueError("Could not extract Google Sheet ID from URL.")

    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    excel_bytes = requests.get(export_url, timeout=REQ_TIMEOUT, headers={"User-Agent": USER_AGENT})
    excel_bytes.raise_for_status()

    raw = pd.read_excel(io.BytesIO(excel_bytes.content), sheet_name=sheet_name, header=None)
    return parse_wow_positions_block(raw, start_row, end_row, source_name="Google Sheet")


@st.cache_data(ttl=60 * 15, show_spinner=False)
def read_local_workbook_block(local_path: str, sheet_name: str, start_row: int, end_row: int) -> WorkbookSource:
    p = Path(local_path)
    if not p.exists():
        raise FileNotFoundError(f"Local workbook not found: {local_path}")
    raw = pd.read_excel(p, sheet_name=sheet_name, header=None)
    return parse_wow_positions_block(raw, start_row, end_row, source_name=p.name)


def parse_wow_positions_block(raw: pd.DataFrame, start_row: int, end_row: int, source_name: str) -> WorkbookSource:
    # Excel/Google Sheet rows are 1-indexed, pandas is 0-indexed
    as_of_date = pd.to_datetime(raw.iloc[3, 2], errors="coerce")
    header_row_idx = start_row  # row 6 in workbook when start_row=5
    data_start_idx = start_row + 1
    data_end_idx = end_row - 1  # exclude total/borrowing row

    headers = raw.iloc[header_row_idx, 1:16].tolist()
    headers = [clean_string(h) for h in headers]

    block = raw.iloc[data_start_idx:data_end_idx, 1:16].copy()
    block.columns = headers
    block = block.rename(columns={
        "Instrument": "Instrument",
        "Instrument ": "Instrument",
        "Cost of Placement": "Cost of Placement",
        "Past Week": "Past Week",
        "Current Week": "Current Week",
        "Gain/Loss": "Gain/Loss",
        "7 Day NAV": "7 Day NAV",
        "NAVs": "NAVs",
        "Number of Units": "Number of Units",
        "Date of Placement": "Date of Placement",
        "Date of Maturity": "Date of Maturity",
        "Weekly Yield": "Weekly Yield",
        "Rate": "Rate",
        "Rate ": "Rate",
        "Days to Maturity": "Days to Maturity",
        "Remaining Days": "Remaining Days",
    })

    for col in [
        "Cost of Placement", "Past Week", "Current Week", "Gain/Loss", "7 Day NAV", "NAVs",
        "Number of Units", "Weekly Yield", "Rate", "Days to Maturity", "Remaining Days"
    ]:
        if col in block.columns:
            block[col] = block[col].apply(safe_float)

    for col in ["Date of Placement", "Date of Maturity"]:
        if col in block.columns:
            block[col] = pd.to_datetime(block[col], errors="coerce")

    block["Instrument"] = block["Instrument"].astype(str).str.strip()
    block = block[block["Instrument"].ne("")].reset_index(drop=True)

    return WorkbookSource(name=source_name, df_block=block, as_of_date=as_of_date)


# -----------------------------
# PKRV ingestion
# -----------------------------
@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def fetch_latest_pkrv_curve() -> pd.DataFrame:
    file_url = find_latest_pkrv_file_url()
    if not file_url:
        raise RuntimeError("Could not locate a PKRV/PKISRV/PKFRV download link on MUFAP.")

    resp = requests.get(file_url, timeout=REQ_TIMEOUT, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()

    lower = file_url.lower()
    if lower.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(resp.content))
    else:
        df = pd.read_excel(io.BytesIO(resp.content))

    curve = normalize_pkrv_dataframe(df)
    if curve.empty:
        raise RuntimeError("PKRV file downloaded, but tenor/yield columns could not be normalized.")
    return curve


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def find_latest_pkrv_file_url() -> Optional[str]:
    pattern = re.compile(r"(pkrv|pkisrv|pkfrv)", re.IGNORECASE)
    candidates: List[str] = []

    for url in MUFAP_PRICING_PAGE_CANDIDATES:
        try:
            resp = requests.get(url, timeout=REQ_TIMEOUT, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a.get("href", "").strip()
                label = clean_string(a.get_text(" ", strip=True))
                full_text = f"{href} {label}"
                if not pattern.search(full_text):
                    continue
                if not re.search(r"\.(csv|xls|xlsx)$", href, re.IGNORECASE):
                    continue
                if href.startswith("/"):
                    href = f"https://www.mufap.com.pk{href}"
                elif href.startswith("http"):
                    pass
                else:
                    href = requests.compat.urljoin(url, href)
                candidates.append(href)
        except Exception:
            continue

    # Prefer PKRV then other curves
    candidates = sorted(set(candidates), key=lambda x: ("pkrv" not in x.lower(), x))
    return candidates[0] if candidates else None



def normalize_pkrv_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work.columns = [clean_string(c).lower() for c in work.columns]

    tenor_col = None
    days_col = None
    yield_col = None

    for c in work.columns:
        if tenor_col is None and ("tenor" in c or c in {"term", "maturity"}):
            tenor_col = c
        if days_col is None and ("day" in c or c in {"days", "remaining days"}):
            days_col = c
        if yield_col is None and ("yield" in c or "rate" == c or c.endswith(" ytm")):
            yield_col = c

    if yield_col is None:
        # brute force numeric search
        numeric_candidates = []
        for c in work.columns:
            ser = pd.to_numeric(work[c], errors="coerce")
            if ser.notna().sum() >= max(3, len(work) // 5):
                numeric_candidates.append(c)
        if numeric_candidates:
            yield_col = numeric_candidates[-1]

    if days_col is None and tenor_col is not None:
        work["_tenor_days"] = work[tenor_col].apply(parse_tenor_to_days)
        days_col = "_tenor_days"

    if days_col is None or yield_col is None:
        return pd.DataFrame(columns=["tenor_days", "yield"])

    work["tenor_days"] = pd.to_numeric(work[days_col], errors="coerce")
    work["yield"] = pd.to_numeric(work[yield_col], errors="coerce")
    work = work.dropna(subset=["tenor_days", "yield"]).copy()
    if work.empty:
        return pd.DataFrame(columns=["tenor_days", "yield"])

    if work["yield"].max() > 1.0:
        work["yield"] = work["yield"] / 100.0

    work = work[(work["tenor_days"] > 0) & (work["yield"] > -1)]
    work = work[["tenor_days", "yield"]].drop_duplicates().sort_values("tenor_days")
    return work.reset_index(drop=True)



def parse_tenor_to_days(value: object) -> Optional[int]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = clean_string(value).upper().replace(" ", "")
    mappings = {
        "1W": 7,
        "2W": 14,
        "1M": 30,
        "2M": 60,
        "3M": 90,
        "4M": 120,
        "5M": 150,
        "6M": 180,
        "9M": 270,
        "12M": 365,
        "1Y": 365,
        "2Y": 730,
        "3Y": 1095,
        "5Y": 1825,
        "10Y": 3650,
    }
    if text in mappings:
        return mappings[text]

    match = re.match(r"^(\d+)([DWMY])$", text)
    if not match:
        return None
    n = int(match.group(1))
    unit = match.group(2)
    factor = {"D": 1, "W": 7, "M": 30, "Y": 365}[unit]
    return n * factor



def interpolated_curve_yield(days: float, curve: pd.DataFrame) -> Optional[float]:
    if curve.empty or days is None or pd.isna(days):
        return None
    curve = curve.sort_values("tenor_days").reset_index(drop=True)

    if days <= curve.loc[0, "tenor_days"]:
        return float(curve.loc[0, "yield"])
    if days >= curve.loc[len(curve) - 1, "tenor_days"]:
        return float(curve.loc[len(curve) - 1, "yield"])

    upper_idx = int(curve[curve["tenor_days"] >= days].index[0])
    lower_idx = upper_idx - 1
    x1 = float(curve.loc[lower_idx, "tenor_days"])
    x2 = float(curve.loc[upper_idx, "tenor_days"])
    y1 = float(curve.loc[lower_idx, "yield"])
    y2 = float(curve.loc[upper_idx, "yield"])
    if x2 == x1:
        return y1
    return y1 + (days - x1) * (y2 - y1) / (x2 - x1)


# -----------------------------
# MUFAP fund performance
# -----------------------------
@st.cache_data(ttl=60 * 60 * 3, show_spinner=False)
def fetch_mufap_fund_performance() -> pd.DataFrame:
    try:
        tables = pd.read_html(MUFAP_PERF_URL)
    except Exception:
        return pd.DataFrame()

    cleaned = []
    for tbl in tables:
        t = tbl.copy()
        t.columns = [clean_string(c) for c in t.columns]
        t = t.dropna(how="all")
        if t.empty:
            continue
        # require a name-like first column and at least one numeric NAV/return field
        joined = " ".join(t.columns).lower()
        if "nav" not in joined and "return" not in joined:
            continue
        cleaned.append(t)

    if not cleaned:
        return pd.DataFrame()

    perf = pd.concat(cleaned, ignore_index=True)
    perf.columns = [clean_string(c) for c in perf.columns]
    return perf


# -----------------------------
# Instrument logic
# -----------------------------
def classify_instrument(name: str) -> str:
    n = clean_string(name).lower()
    if any(x in n for x in ["mtb", "t-bill", "tbill", "t bill"]):
        return "T-Bill"
    if any(x in n for x in ["fund", "plan"]):
        return "Fund"
    if "sukuk" in n:
        return "Sukuk"
    if "coi" in n:
        return "COI"
    if any(x in n for x in ["bank", "placement"]):
        return "Placement"
    return "Other"



def compute_positions_enriched(df: pd.DataFrame, as_of_date: pd.Timestamp, curve: Optional[pd.DataFrame]) -> pd.DataFrame:
    out = df.copy()
    out["Instrument Type"] = out["Instrument"].apply(classify_instrument)

    if "Date of Placement" in out.columns and "Date of Maturity" in out.columns:
        out["Original Term Days"] = (out["Date of Maturity"] - out["Date of Placement"]).dt.days
        out["Days Remaining"] = (out["Date of Maturity"] - as_of_date).dt.days
    else:
        out["Original Term Days"] = np.nan
        out["Days Remaining"] = np.nan

    out["Rate"] = out["Rate"].apply(safe_float)
    out["Weekly Yield"] = out["Weekly Yield"].apply(safe_float)

    out["Implied Face Value"] = np.nan
    out["Purchase Dirty Px /100"] = np.nan
    out["PKRV Yield"] = np.nan
    out["Dirty Px /100"] = np.nan
    out["Curve MV"] = np.nan
    out["Curve Gain/Loss"] = np.nan

    for idx, row in out.iterrows():
        if row["Instrument Type"] != "T-Bill":
            continue
        cost = safe_float(row.get("Cost of Placement"))
        placement_rate = safe_float(row.get("Rate"))
        original_days = safe_float(row.get("Original Term Days"))
        remaining_days = safe_float(row.get("Days Remaining"))
        if cost is None or placement_rate is None or original_days is None or original_days <= 0 or remaining_days is None:
            continue

        purchase_px = 100.0 / (1.0 + placement_rate * original_days / 365.0)
        face = cost * 100.0 / purchase_px
        pkrv_y = interpolated_curve_yield(remaining_days, curve) if curve is not None and not curve.empty else None
        dirty_px = 100.0 / (1.0 + pkrv_y * remaining_days / 365.0) if pkrv_y is not None else np.nan
        curve_mv = face * dirty_px / 100.0 if not pd.isna(dirty_px) else np.nan

        out.at[idx, "Purchase Dirty Px /100"] = purchase_px
        out.at[idx, "Implied Face Value"] = face
        out.at[idx, "PKRV Yield"] = pkrv_y
        out.at[idx, "Dirty Px /100"] = dirty_px
        out.at[idx, "Curve MV"] = curve_mv
        out.at[idx, "Curve Gain/Loss"] = curve_mv - cost if curve_mv is not None and cost is not None else np.nan

    out["Model Current Value"] = out["Current Week"]
    tbill_mask = out["Instrument Type"].eq("T-Bill") & out["Curve MV"].notna()
    out.loc[tbill_mask, "Model Current Value"] = out.loc[tbill_mask, "Curve MV"]
    out["Model Gain/Loss"] = out["Model Current Value"] - out["Cost of Placement"]
    out["Weight"] = out["Cost of Placement"] / out["Cost of Placement"].sum()

    return out


# -----------------------------
# UI helpers
# -----------------------------
def get_source_block(sheet_url: str, local_path: str, start_row: int, end_row: int) -> WorkbookSource:
    errors = []
    try:
        return read_google_sheet_block(sheet_url, SHEET_NAME, start_row, end_row)
    except Exception as exc:
        errors.append(f"Google Sheet load failed: {exc}")

    try:
        return read_local_workbook_block(local_path, SHEET_NAME, start_row, end_row)
    except Exception as exc:
        errors.append(f"Local workbook load failed: {exc}")

    raise RuntimeError(" | ".join(errors))


# -----------------------------
# Main app
# -----------------------------
def main() -> None:
    st.title("NCGCL Fixed Income Dashboard")
    st.caption("Google Sheet-backed holdings monitor with MUFAP peer data and PKRV-based T-bill dirty pricing.")

    with st.sidebar:
        st.header("Controls")
        sheet_url = st.text_input("Google Sheet URL", value=DEFAULT_SHEET_URL)
        local_path = st.text_input("Local workbook fallback", value=DEFAULT_LOCAL_WORKBOOK)
        start_row = st.number_input("Start row", min_value=1, value=DEFAULT_START_ROW, step=1)
        end_row = st.number_input("End row", min_value=2, value=DEFAULT_END_ROW, step=1)
        manual_refresh = st.button("Refresh all")
        if manual_refresh:
            st.cache_data.clear()
        st.markdown("---")
        uploaded_curve = st.file_uploader("Optional PKRV file override (.csv/.xls/.xlsx)", type=["csv", "xls", "xlsx"])

    try:
        source = get_source_block(sheet_url, local_path, int(start_row), int(end_row))
    except Exception as exc:
        st.error(f"Could not load holdings block. {exc}")
        st.stop()

    curve = pd.DataFrame()
    curve_source = "Live MUFAP"
    if uploaded_curve is not None:
        try:
            if uploaded_curve.name.lower().endswith(".csv"):
                curve = pd.read_csv(uploaded_curve)
            else:
                curve = pd.read_excel(uploaded_curve)
            curve = normalize_pkrv_dataframe(curve)
            curve_source = uploaded_curve.name
        except Exception as exc:
            st.warning(f"Uploaded PKRV file could not be parsed: {exc}")

    if curve.empty:
        try:
            curve = fetch_latest_pkrv_curve()
        except Exception as exc:
            st.warning(f"Live PKRV curve could not be fetched from MUFAP: {exc}")
            curve = pd.DataFrame(columns=["tenor_days", "yield"])
            curve_source = "Unavailable"

    positions = compute_positions_enriched(source.df_block, source.as_of_date, curve)

    # Top metrics
    total_cost = positions["Cost of Placement"].sum()
    live_current = positions["Current Week"].sum(skipna=True)
    model_current = positions["Model Current Value"].sum(skipna=True)
    model_gain = positions["Model Gain/Loss"].sum(skipna=True)
    weighted_rate = np.average(positions["Rate"].fillna(0), weights=positions["Cost of Placement"].fillna(0)) if total_cost else np.nan

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("As of date", source.as_of_date.strftime("%d-%b-%Y") if pd.notna(source.as_of_date) else "-")
    m2.metric("Cost Base", fmt_money(total_cost))
    m3.metric("Workbook Current Week", fmt_money(live_current), delta=fmt_money(live_current - total_cost))
    m4.metric("Model Current Week", fmt_money(model_current), delta=fmt_money(model_gain))
    m5.metric("Weighted Cost Yield", fmt_pct(weighted_rate))

    st.markdown(
        f"**Holdings source:** {source.name}  \\  **PKRV source:** {curve_source}"
    )

    tab1, tab2, tab3, tab4 = st.tabs(["Holdings", "T-Bill Pricing", "PKRV Curve", "Peer Funds (MUFAP)"])

    with tab1:
        st.subheader("Positions")
        display_cols = [
            "Instrument", "Instrument Type", "Cost of Placement", "Current Week", "Model Current Value",
            "Model Gain/Loss", "Rate", "Weekly Yield", "Date of Placement", "Date of Maturity", "Days Remaining",
        ]
        display_df = positions[display_cols].copy()
        display_df = display_df.rename(columns={
            "Cost of Placement": "Cost Base",
            "Current Week": "Workbook Current",
            "Model Current Value": "Model Current",
            "Model Gain/Loss": "Model Gain/Loss",
            "Rate": "Booked Rate",
        })
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Cost Base": st.column_config.NumberColumn(format="%.0f"),
                "Workbook Current": st.column_config.NumberColumn(format="%.0f"),
                "Model Current": st.column_config.NumberColumn(format="%.0f"),
                "Model Gain/Loss": st.column_config.NumberColumn(format="%.0f"),
                "Booked Rate": st.column_config.NumberColumn(format="%.2f%%"),
                "Weekly Yield": st.column_config.NumberColumn(format="%.2f%%"),
            },
        )

    with tab2:
        st.subheader("T-Bill Dirty Price Monitor")
        tbills = positions[positions["Instrument Type"].eq("T-Bill")].copy()
        if tbills.empty:
            st.info("No T-bill rows detected in the selected block.")
        else:
            tbill_view = tbills[[
                "Instrument", "Cost of Placement", "Implied Face Value", "Rate", "Date of Placement", "Date of Maturity",
                "Original Term Days", "Days Remaining", "Purchase Dirty Px /100", "PKRV Yield", "Dirty Px /100", "Curve MV",
                "Curve Gain/Loss",
            ]].copy()
            tbill_view = tbill_view.rename(columns={
                "Rate": "Booked Yield",
                "Curve MV": "PKRV MV",
                "Curve Gain/Loss": "PKRV Gain/Loss",
            })
            st.dataframe(
                tbill_view,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Booked Yield": st.column_config.NumberColumn(format="%.2f%%"),
                    "PKRV Yield": st.column_config.NumberColumn(format="%.2f%%"),
                    "Purchase Dirty Px /100": st.column_config.NumberColumn(format="%.4f"),
                    "Dirty Px /100": st.column_config.NumberColumn(format="%.4f"),
                    "Cost of Placement": st.column_config.NumberColumn(format="%.0f"),
                    "Implied Face Value": st.column_config.NumberColumn(format="%.0f"),
                    "PKRV MV": st.column_config.NumberColumn(format="%.0f"),
                    "PKRV Gain/Loss": st.column_config.NumberColumn(format="%.0f"),
                },
            )

            st.markdown("#### Pricing formula used")
            st.code(
                "dirty_price_per_100 = 100 / (1 + interpolated_pkrv_yield * days_remaining / 365)\n"
                "implied_face_value = cost_base * 100 / purchase_dirty_price\n"
                "pkry_curve_mv = implied_face_value * dirty_price_per_100 / 100",
                language="python",
            )

    with tab3:
        st.subheader("PKRV Yield Curve")
        if curve.empty:
            st.info("PKRV curve is not available.")
        else:
            curve_plot = curve.copy()
            curve_plot["tenor_label"] = curve_plot["tenor_days"].astype(int).astype(str) + "D"
            st.line_chart(curve_plot.set_index("tenor_days")["yield"])
            st.dataframe(
                curve_plot.rename(columns={"yield": "Yield", "tenor_days": "Tenor (Days)"}),
                use_container_width=True,
                hide_index=True,
                column_config={"Yield": st.column_config.NumberColumn(format="%.2f%%")},
            )

    with tab4:
        st.subheader("Selected MUFAP Peer Funds")
        perf = fetch_mufap_fund_performance()
        if perf.empty:
            st.info("MUFAP performance table could not be parsed right now.")
        else:
            fund_names = positions.loc[positions["Instrument Type"].eq("Fund"), "Instrument"].dropna().astype(str).tolist()
            if not fund_names:
                st.info("No mutual fund rows detected in the selected holdings block.")
            else:
                mask = pd.Series(False, index=perf.index)
                first_col = perf.columns[0]
                for fund in fund_names:
                    token = re.escape(fund.split("*")[0].strip())
                    if token:
                        mask = mask | perf[first_col].astype(str).str.contains(token, case=False, na=False)
                peer = perf[mask].copy()
                if peer.empty:
                    st.info("No direct name matches found for holdings against MUFAP performance rows.")
                else:
                    st.dataframe(peer, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.caption(
        "Notes: T-bill dirty prices are curve-based and replace workbook current values only for T-bill rows. "
        "Other instruments continue to rely on workbook values/NAVs unless you extend their pricing logic."
    )


if __name__ == "__main__":
    main()
