"""Recurring tab: fixed commitments, subscriptions & bills, fixed vs discretionary, utilities."""

import pandas as pd
import streamlit as st

from src import charts
from src import metrics as m
from src.tabs import section


def render_commitments(df: pd.DataFrame) -> None:
    """Metric cards: average monthly recurring spend, annualised total and share of purchases."""
    rows = m.purchases(df)
    monthly = m.monthly_commitments(df)
    total = rows["amount_aed"].sum()
    recurring = rows.loc[rows["is_recurring"], "amount_aed"].sum()
    cols = st.columns(4)
    cols[0].metric("Avg Monthly Recurring", m.fmt_aed(monthly))
    cols[1].metric("Annualised", m.fmt_aed(None if monthly is None else monthly * 12))
    cols[2].metric(
        "Share of Purchases", m.fmt_pct(recurring / total if total else None, 0),
        help="Recurring spend as a share of all purchase spend",
    )


def render_subscriptions(summary: pd.DataFrame, total_months: int) -> None:
    """Table of recurring merchants sorted by annualised cost."""
    table = summary.assign(
        months_charged=summary["months_charged"].map(lambda n: f"{n} / {total_months}"),
    )[["merchant", "category", "months_charged", "avg_amount", "annualised", "last_charged"]]
    table = table.rename(columns={
        "merchant": "Merchant", "category": "Category", "months_charged": "Months Charged",
        "avg_amount": "Avg Amount", "annualised": "Annualised Cost", "last_charged": "Last Charged",
    })
    styled = table.style.format({
        "Avg Amount": lambda v: m.fmt_aed(v, 2),
        "Annualised Cost": lambda v: m.fmt_aed(v, 2),
        "Last Charged": m.fmt_date,
    })
    st.dataframe(styled, hide_index=True, width="stretch")


def render(df: pd.DataFrame) -> None:
    """Render the Recurring tab."""
    if m.purchases(df).empty:
        st.warning("No purchases match the current filters.")
        return
    summary = m.recurring_summary(df)

    section("Fixed Monthly Commitments", "Recurring = charged in at least 4 months and never more than once a month.")
    render_commitments(df)

    section("Subscriptions & Bills", "Each recurring merchant; annualised cost is the average charge × 12.")
    if summary.empty:
        st.info("No recurring charges in the current selection.")
    else:
        render_subscriptions(summary, df["month"].nunique())

    left, right = st.columns(2)
    with left:
        section("Fixed vs Discretionary", "Monthly purchases split into recurring commitments and everything else.")
        st.plotly_chart(charts.fixed_vs_discretionary_chart(df), width="stretch")
    with right:
        section("Utility Bills Trend", "Monthly DEWA (electricity and water) and du (telecom) bills.")
        if m.purchases(df)["merchant"].isin(charts.UTILITY_MERCHANTS).any():
            st.plotly_chart(charts.utility_bills_chart(df), width="stretch")
        else:
            st.info("No DEWA or du bills in the current selection.")
