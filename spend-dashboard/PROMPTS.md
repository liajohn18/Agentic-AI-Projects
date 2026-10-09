# Spend Dashboard – Claude Code Prompts

How to use this file
- Put `CLAUDE.md` in the project root first. Claude Code reads it automatically.
- Copy **one prompt at a time** into the Claude Code chat in VS Code.
- After each prompt: accept the changes, run or refresh the app, and tick the checks.
- Only move to the next prompt when the checks pass.
- If something breaks, use the **Fix-it prompts** at the bottom.

Before you start (in the VS Code terminal):
```bash
uv init spend-dashboard
cd spend-dashboard
uv add streamlit pandas plotly
mkdir data src src/tabs .streamlit
```
Then copy `transactions.csv` into `data/` and `CLAUDE.md` into the project root.

---

## Prompt 1 – Check the setup

```
Read CLAUDE.md and data/transactions.csv. Confirm the project setup is correct:
uv environment, installed packages, folder structure. Delete main.py if it exists.
Create empty files: app.py, src/__init__.py, src/load.py, src/metrics.py,
src/charts.py, src/tabs/__init__.py. Then give me a short summary of the data
(row count, date range, txn_type counts, total by txn_type). Do not build anything else yet.
```

Checks
- [ ] Summary shows 677 rows, Apr–Sep 2026
- [ ] Purchases ≈ AED 100,700, payments ≈ AED -48,800

---

## Prompt 2 – Merchant map (clean names + categories)

```
Create data/merchant_map.csv with columns: raw_description, merchant, category.
Include one row for every unique value in the description column of
data/transactions.csv.

- merchant = a short clean name (e.g. "UBER *TRIP HELP.UBER.COM" → "Uber",
  "%ARABICA CITY WALK" → "%Arabica", "TALABAT.COM DUBAI AE" → "Talabat").
- category = one of the categories listed in CLAUDE.md.
- GBP / London transactions → Travel. Foreign transaction fees and the annual
  card fee → Fees. "PAYMENT RECEIVED" → Payments. Refund rows → Refunds.

Write the mapping with a Python script so it covers every description, then
list any descriptions where you were unsure of the category so I can review them.
```

Checks
- [ ] Every description has a merchant and a category (no blanks)
- [ ] Open the CSV and fix anything you disagree with

---

## Prompt 3 – Data loader

```
Build src/load.py with a function load_data() decorated with @st.cache_data that:
1. Reads data/transactions.csv and parses txn_date and post_date as dates.
2. Joins data/merchant_map.csv on description = raw_description to add
   merchant and category.
3. Adds columns: month (YYYY-MM), month_name (e.g. "Apr 2026"), weekday name,
   day_of_month, is_weekend (Saturday or Sunday, the UAE weekend), is_foreign
   (original_currency != "AED").
4. Adds is_recurring: True for PURCHASE rows whose merchant appears in at least
   4 of the 6 months.
5. Adds is_duplicate_suspect: True when another PURCHASE has the same txn_date,
   merchant and amount_aed.
6. Adds is_large: True for PURCHASE rows above the 95th percentile of purchase amounts.

Also add a helper filter_data(df, start, end, categories, merchants,
exclude_travel, exclude_large) that returns the filtered dataframe.
Write a quick test script that prints the row count, category totals and the
count of each flag, run it, and show me the output.
```

Checks
- [ ] No row has a missing category
- [ ] The Noon AED 389 pair is flagged as a duplicate suspect
- [ ] Netflix, Spotify, DEWA, du, Fitness First are flagged as recurring

---

## Prompt 4 – KPI functions

```
Build src/metrics.py with these functions. Each takes a dataframe and returns a number.
- total_net_spend: purchases + refunds
- avg_monthly_spend: net spend ÷ number of months in the data
- mom_change: % change in net spend between the latest month and the month before
- txn_count: number of PURCHASE rows
- avg_txn_value: purchase total ÷ purchase count
- top_category: (category name, its share of spend)
- monthly_commitments: average monthly spend on recurring purchases
- delivery_share: Food Delivery spend ÷ total purchase spend
- total_fees: sum of FEE rows
- payment_coverage: abs(payments) ÷ purchases
Add a helper fmt_aed(value, decimals=0) that returns a string like "AED 12,345".
Run each function on the full data and print the results.
```

Checks
- [ ] Payment coverage ≈ 48%
- [ ] Delivery share looks sensible (Talabat + Keeta + Deliveroo)

---

## Prompt 5 – App shell, sidebar and Overview tab

```
Build app.py and src/tabs/overview.py.

app.py:
- st.set_page_config(layout="wide", page_title="Spend Dashboard", page_icon="💳")
- Title "Spend Analysis Dashboard" with a caption showing the date range.
- Sidebar filters: date range (date_input), category multiselect, merchant
  multiselect, toggle "Exclude travel", toggle "Exclude large purchases".
- Create 8 tabs: Overview, Categories, Merchants, Patterns, Recurring,
  Lifestyle, Travel & Fees, Alerts & Explorer.
- Only Overview is implemented. The other tabs show st.info("Coming soon").

Overview tab, with these subheadings:
1. "Key Metrics" – two rows of st.metric cards: Total Spend (with MoM delta),
   Avg Monthly Spend, Transactions, Avg Transaction; Top Category, Monthly
   Commitments, Delivery Share, Fees Paid.
2. "Monthly Spend Trend" – bar chart of net spend per month with a dashed
   line for the average.
3. "Where the Money Goes" – donut of spend by category (exclude Payments, Fees, Refunds).
4. "Spend vs Payments" – grouped bar chart per month.
5. "Key Insights" – 3 auto-generated sentences (highest month and why,
   top category share, payment coverage).

Put chart code in src/charts.py, with one fixed colour per category defined
once as CATEGORY_COLORS. Then tell me the command to run the app.
```

Run it:
```bash
uv run streamlit run app.py
```

Checks
- [ ] Dashboard opens in the browser
- [ ] Filters change the numbers
- [ ] Payments are not in the donut

---

## Prompt 6 – Categories tab

```
Implement the Categories tab in src/tabs/categories.py with these subheadings:
1. "Category Ranking" – horizontal bar chart of spend by category, sorted.
2. "Category Mix Over Time" – stacked bar chart, month × category.
3. "Category → Merchant Breakdown" – treemap.
4. "Category Scorecard" – table: category, spend, transactions, avg ticket,
   share %, MoM change %. Format AED and % nicely.
Use CATEGORY_COLORS from src/charts.py. Respect the sidebar filters.
```

---

## Prompt 7 – Merchants tab

```
Implement the Merchants tab in src/tabs/merchants.py with these subheadings:
1. "Top Merchants" – two charts side by side (st.columns): top 10 by spend,
   top 10 by number of transactions.
2. "Frequency vs Ticket Size" – scatter: x = transactions, y = average ticket,
   bubble size = total spend, colour = category, hover = merchant name.
3. "Merchant Loyalty" – table: merchant, category, months active (out of 6),
   transactions, total spend, sorted by months active.
```

Checks
- [ ] Talabat tops the frequency chart

---

## Prompt 8 – Patterns tab

```
Implement the Patterns tab in src/tabs/patterns.py with these subheadings:
1. "Day-of-Week Pattern" – bar chart of spend and a line of transaction count
   by weekday (Mon→Sun order).
2. "Weekday vs Weekend" – metric cards: avg daily spend on weekdays vs weekends.
3. "Spending Calendar" – heatmap of daily spend (weeks × weekdays, or month × day).
4. "Ticket Size Distribution" – histogram of purchase amounts (cap the x-axis
   at the 99th percentile so outliers don't squash it).
5. "Cumulative Spend Through the Month" – one line per month showing running
   spend by day of month.
```

---

## Prompt 9 – Recurring tab

```
Implement the Recurring tab in src/tabs/recurring.py with these subheadings:
1. "Fixed Monthly Commitments" – metric: average monthly recurring spend,
   and annualised total.
2. "Subscriptions & Bills" – table: merchant, category, months charged,
   average amount, annualised cost, sorted by annualised cost.
3. "Fixed vs Discretionary" – stacked bar per month (recurring vs everything else).
4. "Utility Bills Trend" – line chart of DEWA and du per month.
```

Checks
- [ ] DEWA rises over the summer months

---

## Prompt 10 – Lifestyle tab

```
Implement the Lifestyle tab in src/tabs/lifestyle.py with these subheadings:
1. "Delivery vs Groceries vs Dining Out" – grouped bar per month for Food
   Delivery, Groceries and Dining & Coffee.
2. "Coffee Tracker" – metrics for coffee visits and spend, plus a monthly bar
   chart. Coffee = %Arabica and any other coffee shops in the data.
3. "Delivery Orders per Week" – line chart of weekly order count.
4. "What My Habits Cost per Year" – table projecting annual cost of delivery,
   coffee, dining out and subscriptions from the monthly average.
```

---

## Prompt 11 – Travel & Fees tab

```
Implement the Travel & Fees tab in src/tabs/travel_fees.py with these subheadings:
1. "Foreign Spend Summary" – metrics: total GBP spent, AED equivalent,
   FX fees paid, effective FX cost % (fees ÷ foreign spend).
2. "London Trip Breakdown" – table and bar chart of the GBP transactions
   (date, merchant, GBP, AED, fee).
3. "Card Fees" – table and bar chart of all FEE rows.
4. "Refunds" – table of refunds.
```

---

## Prompt 12 – Alerts & Explorer tab

```
Implement the Alerts & Explorer tab in src/tabs/alerts.py with these subheadings:
1. "Alerts" – three st.expander sections, each showing a count in its title:
   - Possible Duplicates (is_duplicate_suspect)
   - Large Transactions (is_large)
   - Unusual for This Merchant (amount > merchant mean + 2 std, merchants
     with at least 3 transactions)
2. "All Transactions" – a text search box (searches merchant and description),
   then st.dataframe of the filtered transactions with nicely formatted columns,
   and a st.download_button to export the view as CSV.
```

Checks
- [ ] Noon AED 389 duplicate appears
- [ ] Sharaf DG AED 4,299 appears under Large Transactions

---

## Prompt 13 – Polish

```
Polish the whole dashboard:
- Add .streamlit/config.toml with a clean light theme.
- Make sure every chart uses CATEGORY_COLORS and has AED formatting on axes
  and hover labels.
- Add a one-line st.caption under each subheading explaining what it shows.
- Make chart heights consistent and use st.columns where two charts sit well together.
- Remove unused code and make sure there are no warnings in the terminal.
Then review every tab against the sanity checks in CLAUDE.md and report any mismatch.
```

---

## Prompt 14 – README

```
Write README.md for this project: a one-paragraph description, the list of
tabs and what each answers, a "Screenshots" section with placeholders,
setup steps using uv, how to run, the project structure, and a note that the
data is a sample. Also create .gitignore for a Python/uv project.
```

If the data is your real statement, also add `data/transactions.csv` to `.gitignore` before pushing to GitHub.

---

## Fix-it prompts (use any time)

When there's an error:
```
I got this error when running the app. Find the cause and fix it:
<paste the full error here>
```

When a chart looks wrong:
```
In the <tab name> tab, the "<subheading>" chart is wrong: <describe what you see>.
It should <describe what you expect>. Fix it.
```

When a number looks wrong:
```
The <KPI name> shows <value> but I expected about <value>. Show me how it is
calculated, check it against the business rules in CLAUDE.md, and fix it.
```

Before a big change:
```
Before writing any code, show me your plan for: <change>. Wait for my OK.
```

To review everything:
```
Review the whole project for bugs, inconsistent formatting and anything that
breaks the rules in CLAUDE.md. List the issues first, then fix them.
```
