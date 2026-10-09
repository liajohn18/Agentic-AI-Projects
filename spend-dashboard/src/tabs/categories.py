"""Categories tab: ranking, mix over time, merchant breakdown and scorecard."""

import pandas as pd
import streamlit as st

from src import charts
from src import metrics as m
from src.tabs import section


def render_scorecard(df: pd.DataFrame) -> None:
    """Sortable table of per-category stats, formatted for display."""
    card = m.category_scorecard(df).rename(columns={
        "category": "Category", "spend": "Spend", "transactions": "Transactions",
        "avg_ticket": "Avg Ticket", "share": "Share", "mom_change": "MoM Change",
    })
    styled = card.style.format({
        "Spend": lambda v: m.fmt_aed(v, 2),
        "Avg Ticket": lambda v: m.fmt_aed(v, 2),
        "Share": m.fmt_pct,
        "MoM Change": lambda v: m.fmt_pct(v, signed=True),
    })
    st.dataframe(styled, hide_index=True, width="stretch")


def render(df: pd.DataFrame) -> None:
    """Render the Categories tab."""
    if m.purchases(df).empty:
        st.warning("No purchases match the current filters.")
        return

    left, right = st.columns([2, 3])
    with left:
        section("Category Ranking", "Total purchase spend per category, largest first.")
        st.plotly_chart(charts.category_ranking_chart(df), width="stretch")
    with right:
        section("Category Mix Over Time", "Monthly purchase spend stacked by category.")
        st.plotly_chart(charts.category_mix_chart(df), width="stretch")

    section("Category → Merchant Breakdown", "Each box is a merchant sized by spend, grouped by category; click a category to zoom in.")
    st.plotly_chart(charts.category_treemap(df), width="stretch")

    section("Category Scorecard", "Per-category totals; MoM change compares the latest month in the selection with the one before.")
    render_scorecard(df)
