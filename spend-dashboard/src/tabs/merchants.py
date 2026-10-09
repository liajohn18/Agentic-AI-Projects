"""Merchants tab: top merchants, frequency vs ticket size, and loyalty table."""

import pandas as pd
import streamlit as st

from src import charts
from src import metrics as m
from src.tabs import section


def render_loyalty(stats: pd.DataFrame, total_months: int) -> None:
    """Table of merchants sorted by months active, then spend."""
    table = stats.sort_values(["months_active", "spend"], ascending=False)
    table = table.assign(months_active=table["months_active"].map(lambda n: f"{n} / {total_months}"))
    table = table[["merchant", "category", "months_active", "transactions", "spend"]].rename(columns={
        "merchant": "Merchant", "category": "Category", "months_active": "Months Active",
        "transactions": "Transactions", "spend": "Total Spend",
    })
    styled = table.style.format({"Total Spend": lambda v: m.fmt_aed(v, 2)})
    st.dataframe(styled, hide_index=True, width="stretch")


def render(df: pd.DataFrame) -> None:
    """Render the Merchants tab."""
    stats = m.merchant_stats(df)
    if stats.empty:
        st.warning("No purchases match the current filters.")
        return

    section("Top Merchants", "The ten merchants with the most spend and the most purchases, coloured by category.")
    left, right = st.columns(2)
    with left:
        st.markdown("**By spend**")
        st.plotly_chart(charts.top_merchants_by_spend_chart(stats), width="stretch")
    with right:
        st.markdown("**By number of transactions**")
        st.plotly_chart(charts.top_merchants_by_count_chart(stats), width="stretch")

    section("Frequency vs Ticket Size", "One bubble per merchant, sized by total spend; both axes are log scale.")
    st.plotly_chart(charts.frequency_vs_ticket_chart(stats), width="stretch")

    section("Merchant Loyalty", "How many months of the selection each merchant was used, most regular first.")
    render_loyalty(stats, df["month"].nunique())
