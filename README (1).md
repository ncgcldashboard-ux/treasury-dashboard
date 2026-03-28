# Corporate Dashboard — Setup Guide

## How it works

```
Google Sheets  →  Apps Script (your free API)  →  dashboard.html (GitHub Pages)
```

No API keys. No backend server. Completely free.

---

## Step 1 — Set up the Apps Script API

1. Open your Google Sheet
2. Click **Extensions → Apps Script**
3. Delete any existing code
4. Paste the entire contents of `apps-script-code.gs` into the editor
5. Click **Save** (floppy disk icon or Ctrl+S)
6. Click **Deploy → New Deployment**
7. Click the gear icon next to "Type" and choose **Web App**
8. Set **Execute as:** `Me`
9. Set **Who has access:** `Anyone`
10. Click **Deploy**
11. Copy the **Web App URL** — it looks like:
    `https://script.google.com/macros/s/XXXXXXXXX/exec`

---

## Step 2 — Deploy the dashboard to GitHub Pages

1. Create a new GitHub repository (e.g. `my-dashboard`)
2. Upload `dashboard.html` — **rename it to `index.html`**
3. Go to **Settings → Pages**
4. Under "Source", select **Deploy from a branch → main → / (root)**
5. Click **Save**
6. Your dashboard will be live at:
    `https://YOUR-USERNAME.github.io/my-dashboard/`

---

## Step 3 — Connect the dashboard to your Sheet

1. Open your GitHub Pages URL
2. Paste your Apps Script Web App URL into the input bar
3. Click **Connect**

The URL is saved in your browser automatically — you only need to do this once.

---

## How your Sheet should be structured

The dashboard auto-detects your columns. For best results:

| Name (text) | Revenue (number) | Region (text) | ... |
|-------------|-----------------|---------------|-----|
| Acme Corp   | 120000          | North America | ... |
| Globex      | 85000           | Europe        | ... |

- **Text columns** → used as labels in the table and bar chart
- **Numeric columns** → used for KPI totals, averages, and trend chart
- **Multiple sheet tabs** → each tab becomes a clickable button on the dashboard

---

## Features

- Live data from Google Sheets (auto-refreshes every 60 seconds)
- Multi-sheet support — switch between tabs with one click
- KPI cards: row count, sum, average, column count
- Data table (first 20 rows)
- Top values bar chart (top 8 by numeric value)
- Trend line chart
- URL remembered in browser — no re-pasting after first connect

---

## Troubleshooting

**"Error: Failed to fetch"**
→ Make sure the Apps Script is deployed with "Anyone" access (not "Anyone with Google account")

**"HTTP 401" or "HTTP 403"**
→ Re-deploy the Apps Script. Go to Deploy → Manage Deployments → edit → bump version → Deploy again.

**Data looks wrong**
→ Make sure row 1 of your sheet is a header row (column names).

**Changes not showing**
→ If you edit the Apps Script code itself, you must create a **New Deployment** each time (not re-use the old one). Just pasting new data into the sheet works instantly.
