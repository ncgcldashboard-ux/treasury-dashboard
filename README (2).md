# NCGCL Treasury Dashboard

**Live URL:** https://ncgcldashboard-ux.github.io/treasury-dashboard/

A corporate fund operations dashboard for NCGCL's treasury team. It reads directly from an Excel file (`data.xlsx`) stored in this GitHub repository — no backend, no API keys, no login required.

---

## How It Works

```
You upload data.xlsx to this repo
        ↓
GitHub hosts it at a public raw URL
        ↓
dashboard (index.html) fetches it via SheetJS on every page load
        ↓
All charts, tables, and KPIs render automatically
```

The dashboard auto-loads when the page opens. It displays a **File Date** (when the xlsx was last uploaded to GitHub) and a **Last Refreshed** timestamp (when the browser fetched it).

---

## Repository Structure

```
treasury-dashboard/
├── index.html        ← The dashboard (do not rename)
├── data.xlsx         ← Your Excel data file (update this to refresh data)
└── README.md         ← This file
```

---

## How to Update Data

1. Open your Excel workbook and update the data
2. Save it as `data.xlsx`
3. Go to this GitHub repo in your browser
4. Click on `data.xlsx` → click the pencil/upload icon → upload the new file → commit
5. Wait ~30 seconds for GitHub to process, then refresh the dashboard

> **Tip:** The dashboard shows the file's last-modified date so you always know how current the data is.

---

## Excel File Structure

The dashboard reads three sheets from `data.xlsx`:

### Sheet 1 — `WoW Positions` (required)
This is the main positions sheet. The dashboard auto-detects the header row by looking for the word **"Instrument"**.

Expected columns (order does not matter, matched by name):

| Column | Description |
|--------|-------------|
| Instrument | Name of the investment |
| Cost of Placement | Original cost |
| Past Week | Prior week valuation |
| Current Week | This week valuation |
| Gain/Loss | Weekly P&L |
| 1 Day Returns | 1-day annualised return |
| 15 Day Returns | 15-day annualised return |
| 30 Day Returns | 30-day annualised return |
| 90 Day Returns | 90-day annualised return |
| Weekly Yield | Weekly yield rate (already as %) |
| Rate | Gross rate (already as %) |
| Tax Adjusted Rate - 1 Day | Already as % |
| Gross Expectation | Already as % |
| Tax Adjusted Rate - 30 Day | Already as % |
| Concentration (%) | Portfolio weight |
| PVBP | Price value of a basis point |
| Modified Duration | Interest rate sensitivity |
| Convexity | Convexity measure |
| Tenor | Instrument tenor (3M, 6M, 1Y, etc.) |
| Secondary Yields | Secondary market yields (as %) |
| Dirty Pricing | Dirty price value |
| Days to Maturity | Total tenor in days |
| Remaining Days | Days until maturity |
| Date of Placement | Start date |
| Date of Maturity | End date |

**Special rows** (detected automatically by instrument name):

| Row label | What it contains |
|-----------|-----------------|
| `Total` | Portfolio totals row |
| `Borrowing` | Financing liability |
| `NAV` | Clean NAV — past week (col 3) and current week (col 4) |
| `NAV Units` | Units outstanding |
| `Benchmark` | Benchmark return % (col 3) |
| `Alpha` | Alpha vs benchmark % (col 3) — displayed as-is, already a % |
| `3MK` | 3-month KIBOR % (col 3) |

**Net Weekly Gain** is computed as:
```
Net Gain = Total Gain/Loss (assets) − |Borrowing Gain/Loss|
```

### Sheet 2 — `PKRV` (optional but recommended)
The PKRV sheet powers the **PKRV Yield Curve** chart on the Overview tab.

Expected format — one row per date, tenor names as column headers:

| Date | 3M | 6M | 1Y | 2Y | 3Y | 5Y | 7Y | 10Y |
|------|----|----|----|----|----|----|-----|------|
| 28-Mar-26 | 11.50 | 11.44 | 11.72 | 11.80 | 11.90 | 12.00 | 12.10 | 12.20 |

The dashboard reads the **most recent row** (last non-empty row) as the current yield curve.

Yield values should be in percentage form (e.g. `11.72` for 11.72%).

> If the PKRV sheet is not present, the dashboard falls back to showing secondary yields extracted from the WoW Positions sheet.

### Sheet 3 — `Dashboard` (optional)
Any additional summary data you want to preserve. Not currently rendered but will not cause errors.

---

## Dashboard Sections

### KPI Strip (top)
| KPI | Source |
|-----|--------|
| Gross AUM | `Total` row → Current Week |
| Net Weekly Gain | Gross Gain/Loss minus Borrowing cost |
| Portfolio Yield | `Total` row → Weekly Yield |
| NAV (Clean) | `NAV` row → Current Week column |
| NAV (Dirty) | `NAV` row → last value column |
| Instruments | Count of active position rows |

### Overview Tab
- **Insights row:** Clean NAV vs prior week · Net gain after borrowing · Alpha vs benchmark
- **Concentration chart:** Doughnut by % of AUM
- **Weekly Yield chart:** Bar chart per instrument (values already as %)
- **WoW Value chart:** Current vs prior week for top 8 positions
- **PKRV Yield Curve:** Line chart from PKRV sheet (or secondary yields fallback)

### WoW Positions Tab
- Full positions table with type pills, costs, valuations, gain/loss (green/red), yield, concentration, remaining days
- Liabilities table showing borrowing cost and maturity
- Net summary table showing gross gain → borrowing cost → net gain

### Return Rates Tab
- All return columns per instrument — values shown as-is (already stored as %)
- Multi-period return comparison chart (1D / 30D / 90D)
- Gain/Loss per instrument bar chart

### Fund Metrics Tab
- Clean NAV (past vs current) + Dirty NAV + units outstanding
- Benchmark, Alpha (displayed as reported), 3M KIBOR, net annualised yield
- Full risk metrics table: PVBP, Modified Duration, Convexity, Secondary Yields, Dirty Price

---

## Refreshing the Dashboard

The dashboard auto-loads on every page open. To manually force a reload, click the **↻ Refresh** button in the status bar.

The status bar shows:
- **File date:** When `data.xlsx` was last committed to GitHub (from HTTP headers)
- **Last refreshed:** When the browser last fetched the file

---

## Technical Notes

- Built with vanilla HTML/CSS/JS — no frameworks, no build step
- **SheetJS** (xlsx.js) parses the Excel file in the browser
- **Chart.js** renders all charts
- Both libraries loaded from Cloudflare CDN — no npm required
- The xlsx URL is hardcoded in `index.html` at the top of the `<script>` block:
  ```js
  const XLSX_URL = 'https://raw.githubusercontent.com/ncgcldashboard-ux/treasury-dashboard/main/data.xlsx';
  ```
  Change this if you rename the file or move the repo.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "HTTP 404" error | The `data.xlsx` file doesn't exist in the repo yet — upload it |
| "HTTP 403" error | The repository is set to Private — change to Public in Settings |
| Data looks wrong / blank | Check that your sheet is named `WoW Positions` and has an `Instrument` header row |
| PKRV chart shows fallback message | Add a sheet named `PKRV` to your Excel file (see format above) |
| File date shows "not available" | GitHub CDN doesn't always return Last-Modified headers — this is normal |
| Charts don't render | Hard-refresh the page (Ctrl+Shift+R) to clear any cached JS |

---

## Maintainer

NCGCL · Treasury & Investments  
Dashboard version: March 2026  
Confidential — Internal Use Only
