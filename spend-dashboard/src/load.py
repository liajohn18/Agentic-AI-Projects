"""Load, clean and enrich the transaction data."""

from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECURRING_MIN_MONTHS = 4
LARGE_QUANTILE = 0.95


def read_transactions() -> pd.DataFrame:
    """Read transactions.csv with date columns parsed."""
    return pd.read_csv(DATA_DIR / "transactions.csv", parse_dates=["txn_date", "post_date"])


def add_merchant_info(df: pd.DataFrame) -> pd.DataFrame:
    """Join merchant and category from merchant_map.csv."""
    merchant_map = pd.read_csv(DATA_DIR / "merchant_map.csv")
    out = df.merge(
        merchant_map, left_on="description", right_on="raw_description",
        how="left", validate="many_to_one",
    ).drop(columns="raw_description")
    missing = out.loc[out["merchant"].isna(), "description"].unique()
    if len(missing):
        raise ValueError(f"Descriptions missing from merchant_map.csv: {list(missing)}")
    return out


def add_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add month, month_name, weekday, day_of_month and is_weekend."""
    dates = df["txn_date"]
    return df.assign(
        month=dates.dt.strftime("%Y-%m"),
        month_name=dates.dt.strftime("%b %Y"),
        weekday=dates.dt.day_name(),
        day_of_month=dates.dt.day,
        is_weekend=dates.dt.dayofweek >= 5,  # Sat/Sun is the UAE weekend
    )


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Add is_foreign, is_recurring, is_duplicate_suspect and is_large."""
    is_purchase = df["txn_type"] == "PURCHASE"
    purchases = df[is_purchase]

    # Recurring = billed in at least 4 months and never more than once in a month
    # (subscriptions and bills), which excludes everyday merchants like coffee shops.
    per_month = purchases.groupby(["merchant", "month"]).size().groupby("merchant")
    months_active, max_per_month = per_month.size(), per_month.max()
    recurring = months_active[(months_active >= RECURRING_MIN_MONTHS) & (max_per_month == 1)].index
    duplicates = purchases.duplicated(["txn_date", "merchant", "amount_aed"], keep=False)
    large_threshold = purchases["amount_aed"].quantile(LARGE_QUANTILE)

    return df.assign(
        is_foreign=df["original_currency"] != "AED",
        is_recurring=is_purchase & df["merchant"].isin(recurring),
        is_duplicate_suspect=duplicates.reindex(df.index, fill_value=False),
        is_large=is_purchase & (df["amount_aed"] > large_threshold),
    )


@st.cache_data
def load_data() -> pd.DataFrame:
    """Return the fully enriched transactions dataframe."""
    df = read_transactions()
    df = add_merchant_info(df)
    df = add_date_columns(df)
    return add_flags(df)


def filter_data(
    df: pd.DataFrame,
    start,
    end,
    categories=None,
    merchants=None,
    exclude_travel: bool = False,
    exclude_large: bool = False,
) -> pd.DataFrame:
    """Filter by txn_date range (inclusive), categories, merchants and exclusions.

    Empty or None categories/merchants mean no filter on that column.
    """
    mask = df["txn_date"].between(pd.Timestamp(start), pd.Timestamp(end))
    if categories:
        mask &= df["category"].isin(categories)
    if merchants:
        mask &= df["merchant"].isin(merchants)
    if exclude_travel:
        mask &= df["category"] != "Travel"
    if exclude_large:
        mask &= ~df["is_large"]
    return df[mask]
