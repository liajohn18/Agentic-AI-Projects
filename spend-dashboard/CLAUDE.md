# Spend Analysis Dashboard

## Goal
A Streamlit dashboard that analyses one cardholder's credit card transactions
(1 Apr – 30 Sep 2026, amounts in AED) from `data/transactions.csv`.
It should show where money goes, spending habits, recurring commitments,
travel and fees, and anything unusual worth checking.

## Stack and rules
- Python project managed with **uv**. Add packages with `uv add <pkg>`, never pip.
- Run the app with: `uv run streamlit run app.py`
- **pandas** for data, **Plotly Express / graph_objects** for every chart.
- `st.tabs` for tabs, `st.sidebar` for filters, `st.metric` for KPIs.
- Cache data loading with `@st.cache_data`.
- Page layout: `st.set_page_config(layout="wide", page_title="Spend Dashboard")`.
- Format money as `AED 12,345` (no decimals in KPIs, 2 decimals in tables).
- One fixed colour per category, defined once in `src/charts.py` and reused everywhere.
- Keep functions small and readable. Add a short docstring to each function.
- Build one step at a time. Do not build tabs that were not asked for yet.

## Data
File: `data/transactions.csv` (677 rows, no missing values)

| Column | Meaning |
|---|---|
| txn_id | Unique ID (T00001…) |
| txn_date | Date of transaction (YYYY-MM-DD) |
| post_date | Date posted to the card |
| description | Raw merchant text, e.g. "UBER *TRIP HELP.UBER.COM" |
| amount_aed | Amount in AED. Positive = spend, negative = payment or refund |
| original_currency | AED or GBP |
| original_amount | Amount in original currency |
| txn_type | PURCHASE, PAYMENT, FEE, REFUND |

## Business rules
- **Spend** = PURCHASE rows.
- **Net spend** = purchases + refunds (refunds are negative amounts).
- **PAYMENT rows are never counted as spend.** They are card bill payments.
- **FEE rows** (annual fee, foreign transaction fees) are tracked separately.
- Clean merchant names and categories come from `data/merchant_map.csv`.
- GBP transactions are a London trip → category **Travel**.

## Categories
Food Delivery, Groceries, Dining & Coffee, Online Shopping, Retail & Fashion,
Utilities & Telecom, Subscriptions, Health & Fitness, Transport,
Entertainment, Travel, Fees, Payments, Refunds

## Project structure
```
app.py              entry point: page config, sidebar filters, tabs
data/
  transactions.csv
  merchant_map.csv  raw_description → merchant, category
src/
  load.py           load, clean, enrich data
  metrics.py        KPI calculations
  charts.py         one function per chart, each returns a Plotly figure
  tabs/             one file per tab, each with render(df)
.streamlit/config.toml
```

## Tabs
1. Overview
2. Categories
3. Merchants
4. Patterns
5. Recurring
6. Lifestyle
7. Travel & Fees
8. Alerts & Explorer

## Sanity checks (use these to verify work)
- Total purchases ≈ AED 100,700; payments ≈ AED 48,800 (6 payments).
- Talabat is the most frequent merchant (98 transactions).
- Two identical Noon.com charges of AED 389 on 2026-05-16 → possible duplicate.
- Largest purchase: Sharaf DG Dubai Mall, AED 4,299 (2026-06-07).
- 5 GBP transactions in London, 3–7 Aug 2026, each with a foreign transaction fee.
