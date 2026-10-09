"""Spend Analysis Dashboard entry point. Run with: uv run streamlit run app.py"""

import streamlit as st

from src.load import filter_data, load_data
from src.tabs import alerts, categories, lifestyle, merchants, overview, patterns, recurring, travel_fees

TABS = {
    "Overview": overview,
    "Categories": categories,
    "Merchants": merchants,
    "Patterns": patterns,
    "Recurring": recurring,
    "Lifestyle": lifestyle,
    "Travel & Fees": travel_fees,
    "Alerts & Explorer": alerts,
}


def sidebar_filters(df):
    """Draw sidebar filters and return the filtered dataframe and chosen date range."""
    st.sidebar.header("Filters")
    min_date, max_date = df["txn_date"].min().date(), df["txn_date"].max().date()
    dates = st.sidebar.date_input(
        "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date,
    )
    # While the user is mid-selection only one date is returned.
    start, end = dates if len(dates) == 2 else (min_date, max_date)

    categories = st.sidebar.multiselect(
        "Categories", sorted(df["category"].unique()), placeholder="All categories",
    )
    merchant_pool = df[df["category"].isin(categories)] if categories else df
    merchants = st.sidebar.multiselect(
        "Merchants", sorted(merchant_pool["merchant"].unique()), placeholder="All merchants",
    )
    exclude_travel = st.sidebar.toggle("Exclude travel")
    exclude_large = st.sidebar.toggle("Exclude large purchases")

    filtered = filter_data(df, start, end, categories, merchants, exclude_travel, exclude_large)
    return filtered, start, end


def main() -> None:
    """Build the page: config, title, filters and tabs."""
    st.set_page_config(layout="wide", page_title="Spend Dashboard", page_icon="💳")
    df = load_data()
    filtered, start, end = sidebar_filters(df)

    st.title("Spend Analysis Dashboard")
    st.caption(
        f"{start:%d %b %Y} – {end:%d %b %Y} · {len(filtered):,} transactions · amounts in AED"
    )

    for tab, module in zip(st.tabs(list(TABS)), TABS.values(), strict=True):
        with tab:
            module.render(filtered)


main()
