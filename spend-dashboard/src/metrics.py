"""KPI calculations. Each function takes the enriched dataframe from load_data().

Shares and changes are returned as fractions (0.25 = 25%). Functions return None
when the value cannot be computed (e.g. no purchases in the filtered data).
"""

import pandas as pd


def purchases(df: pd.DataFrame) -> pd.DataFrame:
    """Return PURCHASE rows only."""
    return df[df["txn_type"] == "PURCHASE"]


def _ratio(numerator: float, denominator: float) -> float | None:
    """Divide, returning None when the denominator is zero."""
    return numerator / denominator if denominator else None


def monthly_net_spend(df: pd.DataFrame) -> pd.Series:
    """Net spend (purchases + refunds) per month, sorted by month."""
    net = df[df["txn_type"].isin(["PURCHASE", "REFUND"])]
    return net.groupby("month")["amount_aed"].sum().sort_index()


def total_net_spend(df: pd.DataFrame) -> float:
    """Purchases plus refunds (refunds are negative)."""
    return float(monthly_net_spend(df).sum())


def avg_monthly_spend(df: pd.DataFrame) -> float | None:
    """Net spend divided by the number of months in the data."""
    return _ratio(total_net_spend(df), df["month"].nunique())


def mom_change(df: pd.DataFrame) -> float | None:
    """Fractional change in net spend from the previous month to the latest month."""
    monthly = monthly_net_spend(df)
    if len(monthly) < 2:
        return None
    return _ratio(monthly.iloc[-1] - monthly.iloc[-2], monthly.iloc[-2])


def txn_count(df: pd.DataFrame) -> int:
    """Number of PURCHASE rows."""
    return len(purchases(df))


def avg_txn_value(df: pd.DataFrame) -> float | None:
    """Average purchase amount."""
    rows = purchases(df)
    return _ratio(rows["amount_aed"].sum(), len(rows))


def top_category(df: pd.DataFrame) -> tuple[str, float] | None:
    """Category with the most purchase spend and its share of purchase spend."""
    by_category = purchases(df).groupby("category")["amount_aed"].sum()
    if by_category.empty or by_category.sum() == 0:
        return None
    return by_category.idxmax(), float(by_category.max() / by_category.sum())


def monthly_commitments(df: pd.DataFrame) -> float | None:
    """Average monthly spend on recurring purchases."""
    recurring = purchases(df).loc[lambda d: d["is_recurring"], "amount_aed"].sum()
    return _ratio(float(recurring), df["month"].nunique())


def delivery_share(df: pd.DataFrame) -> float | None:
    """Food Delivery spend as a share of total purchase spend."""
    rows = purchases(df)
    delivery = rows.loc[rows["category"] == "Food Delivery", "amount_aed"].sum()
    return _ratio(float(delivery), rows["amount_aed"].sum())


def total_fees(df: pd.DataFrame) -> float:
    """Sum of FEE rows."""
    return float(df.loc[df["txn_type"] == "FEE", "amount_aed"].sum())


def payment_coverage(df: pd.DataFrame) -> float | None:
    """Card payments as a share of purchases."""
    payments = df.loc[df["txn_type"] == "PAYMENT", "amount_aed"].sum()
    return _ratio(abs(float(payments)), purchases(df)["amount_aed"].sum())


def category_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    """Per-category purchase spend, count, avg ticket, share and MoM change.

    MoM change compares the latest month in the data with the month before it
    (NaN when a category had no spend in the earlier month).
    """
    rows = purchases(df)
    card = rows.groupby("category")["amount_aed"].agg(spend="sum", transactions="count")
    card["avg_ticket"] = card["spend"] / card["transactions"]
    card["share"] = card["spend"] / card["spend"].sum()

    months = sorted(rows["month"].unique())
    card["mom_change"] = float("nan")
    if len(months) >= 2:
        monthly = rows.pivot_table(
            index="category", columns="month", values="amount_aed", aggfunc="sum", fill_value=0,
        )
        latest, previous = monthly[months[-1]], monthly[months[-2]].replace(0, float("nan"))
        card["mom_change"] = (latest - previous) / previous
    return card.sort_values("spend", ascending=False).reset_index()


def merchant_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Per-merchant purchase stats: category, transactions, spend, avg ticket, months active."""
    stats = purchases(df).groupby(["merchant", "category"], as_index=False).agg(
        transactions=("amount_aed", "count"),
        spend=("amount_aed", "sum"),
        months_active=("month", "nunique"),
    )
    stats["avg_ticket"] = stats["spend"] / stats["transactions"]
    return stats


def recurring_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Recurring merchants: category, months charged, average amount and annualised cost."""
    rows = purchases(df)
    rows = rows[rows["is_recurring"]]
    summary = rows.groupby(["merchant", "category"], as_index=False).agg(
        months_charged=("month", "nunique"),
        avg_amount=("amount_aed", "mean"),
        last_charged=("txn_date", "max"),
    )
    summary["annualised"] = summary["avg_amount"] * 12
    return summary.sort_values("annualised", ascending=False)


COFFEE_MERCHANTS = ["%Arabica", "Starbucks", "Tim Hortons"]


def coffee_purchases(df: pd.DataFrame) -> pd.DataFrame:
    """Purchases at coffee shops."""
    rows = purchases(df)
    return rows[rows["merchant"].isin(COFFEE_MERCHANTS)]


def habit_groups(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Purchase rows for each lifestyle habit (coffee is split out of Dining & Coffee)."""
    rows = purchases(df)
    is_coffee = rows["merchant"].isin(COFFEE_MERCHANTS)
    return {
        "Food delivery": rows[rows["category"] == "Food Delivery"],
        "Coffee": rows[is_coffee],
        "Dining out": rows[(rows["category"] == "Dining & Coffee") & ~is_coffee],
        "Subscriptions": rows[rows["category"] == "Subscriptions"],
    }


def habit_costs(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly average and projected annual cost of each habit."""
    months = df["month"].nunique() or 1
    records = [
        {
            "habit": name,
            "transactions_per_month": len(rows) / months,
            "monthly_avg": rows["amount_aed"].sum() / months,
        }
        for name, rows in habit_groups(df).items()
    ]
    costs = pd.DataFrame(records)
    costs["annual"] = costs["monthly_avg"] * 12
    return costs


def weekly_delivery_orders(df: pd.DataFrame) -> pd.Series:
    """Food Delivery order count per week (weeks start Monday), 0 for weeks with none."""
    rows = purchases(df)
    rows = rows[rows["category"] == "Food Delivery"]
    if rows.empty:
        return pd.Series(dtype=int)
    week = rows["txn_date"].dt.to_period("W-SUN").dt.start_time
    counts = week.value_counts().sort_index()
    all_weeks = pd.date_range(counts.index.min(), counts.index.max(), freq="W-MON")
    return counts.reindex(all_weeks, fill_value=0)


FX_FEE_PREFIX = "FOREIGN TRANSACTION FEE "


def fee_rows(df: pd.DataFrame) -> pd.DataFrame:
    """FEE rows only."""
    return df[df["txn_type"] == "FEE"]


def foreign_purchases_with_fees(df: pd.DataFrame) -> pd.DataFrame:
    """Foreign-currency purchases, each matched to its foreign transaction fee.

    A fee matches a purchase on the same txn_date whose description starts with
    the word after "FOREIGN TRANSACTION FEE" (e.g. "... FEE DISHOOM" -> "DISHOOM ...").
    """
    foreign = purchases(df)
    foreign = foreign[foreign["is_foreign"]]
    fx_fees = fee_rows(df)
    fx_fees = fx_fees[fx_fees["description"].str.startswith(FX_FEE_PREFIX)]
    fees_by_key = (
        fx_fees.assign(fee_key=fx_fees["description"].str.removeprefix(FX_FEE_PREFIX))
        .groupby(["txn_date", "fee_key"], as_index=False)["amount_aed"].sum()
        .rename(columns={"amount_aed": "fx_fee"})
    )
    foreign = (
        foreign.assign(fee_key=foreign["description"].str.split().str[0])
        .merge(fees_by_key, on=["txn_date", "fee_key"], how="left")
        .drop(columns="fee_key")
    )
    foreign["fx_fee"] = foreign["fx_fee"].fillna(0.0)
    foreign["rate"] = foreign["amount_aed"] / foreign["original_amount"]
    return foreign.sort_values("txn_date")


def fx_summary(df: pd.DataFrame) -> dict[str, float | None]:
    """Totals for foreign spend: original amount, AED equivalent, FX fees and effective cost."""
    foreign = foreign_purchases_with_fees(df)
    fx_fees = fee_rows(df)
    fx_fees = fx_fees.loc[fx_fees["description"].str.startswith(FX_FEE_PREFIX), "amount_aed"].sum()
    aed = foreign["amount_aed"].sum()
    return {
        "original": float(foreign["original_amount"].sum()),
        "aed": float(aed),
        "fees": float(fx_fees),
        "effective_cost": _ratio(float(fx_fees), float(aed)),
    }


def unusual_for_merchant(df: pd.DataFrame, min_txns: int = 3, n_std: float = 2.0) -> pd.DataFrame:
    """Purchases above their merchant's mean + n_std standard deviations.

    Only merchants with at least min_txns purchases are checked. Adds merchant_mean,
    merchant_std and times_mean columns.
    """
    rows = purchases(df)
    stats = rows.groupby("merchant")["amount_aed"].agg(merchant_mean="mean", merchant_std="std", n="count")
    rows = rows.join(stats, on="merchant")
    unusual = rows[(rows["n"] >= min_txns) & (rows["amount_aed"] > rows["merchant_mean"] + n_std * rows["merchant_std"])]
    unusual = unusual.assign(times_mean=unusual["amount_aed"] / unusual["merchant_mean"])
    return unusual.drop(columns="n").sort_values("times_mean", ascending=False)


def search_transactions(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Rows whose merchant or description contains query (case-insensitive)."""
    query = query.strip()
    if not query:
        return df
    hit = (
        df["merchant"].str.contains(query, case=False, regex=False)
        | df["description"].str.contains(query, case=False, regex=False)
    )
    return df[hit]


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def daily_spend(df: pd.DataFrame) -> pd.Series:
    """Purchase spend for every calendar day in the data's date range (0 on no-spend days)."""
    if df.empty:
        return pd.Series(dtype=float)
    days = pd.date_range(df["txn_date"].min(), df["txn_date"].max(), freq="D")
    return purchases(df).groupby("txn_date")["amount_aed"].sum().reindex(days, fill_value=0.0)


def weekday_weekend_avg(df: pd.DataFrame) -> tuple[float | None, float | None]:
    """Average daily purchase spend on weekdays (Mon–Fri) and weekends (Sat–Sun)."""
    daily = daily_spend(df)
    weekend = daily.index.dayofweek >= 5
    weekday_avg = daily[~weekend].mean() if (~weekend).any() else None
    weekend_avg = daily[weekend].mean() if weekend.any() else None
    return weekday_avg, weekend_avg


def fmt_aed(value: float | None, decimals: int = 0) -> str:
    """Format a number as 'AED 12,345' (or '—' when missing)."""
    if value is None:
        return "—"
    return f"AED {value:,.{decimals}f}"


def fmt_pct(value: float | None, decimals: int = 1, signed: bool = False) -> str:
    """Format a fraction as a percentage, e.g. 0.125 -> '12.5%' (or '—' when missing)."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:{'+' if signed else ''}.{decimals}%}"


def fmt_date(value) -> str:
    """Format a date as '05 Aug 2026'."""
    return f"{value:%d %b %Y}"
