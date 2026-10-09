"""Lifestyle tab: food spend mix, coffee tracker, delivery frequency and habit costs."""

import pandas as pd
import streamlit as st

from src import charts
from src import metrics as m
from src.tabs import section

HABIT_NOTES = {
    "Food delivery": "Talabat, Deliveroo, Keeta",
    "Coffee": ", ".join(m.COFFEE_MERCHANTS),
    "Dining out": "Dining & Coffee, excluding coffee shops",
    "Subscriptions": "Streaming, music and cloud storage",
}


def render_coffee(df: pd.DataFrame) -> None:
    """Coffee metric cards (2 × 2) and monthly spend chart."""
    coffee = m.coffee_purchases(df)
    if coffee.empty:
        st.info("No coffee purchases in the current selection.")
        return
    days = (df["txn_date"].max() - df["txn_date"].min()).days + 1
    row1, row2 = st.columns(2), st.columns(2)
    row1[0].metric("Coffee Visits", f"{len(coffee):,}")
    row1[1].metric("Coffee Spend", m.fmt_aed(coffee["amount_aed"].sum()))
    row2[0].metric("Avg per Visit", m.fmt_aed(coffee["amount_aed"].mean()))
    row2[1].metric("Visits per Week", f"{len(coffee) / days * 7:.1f}")
    st.plotly_chart(charts.coffee_monthly_chart(df), width="stretch")


def render_habit_costs(df: pd.DataFrame) -> None:
    """Table projecting the annual cost of each habit from its monthly average."""
    costs = m.habit_costs(df)
    total = {"habit": "Total", **costs[["transactions_per_month", "monthly_avg", "annual"]].sum().to_dict()}
    costs = pd.concat([costs, pd.DataFrame([total])], ignore_index=True)
    costs.insert(1, "includes", costs["habit"].map(HABIT_NOTES).fillna(""))
    table = costs.rename(columns={
        "habit": "Habit", "includes": "Includes", "transactions_per_month": "Purchases / Month",
        "monthly_avg": "Avg per Month", "annual": "Projected per Year",
    })
    styled = table.style.format({
        "Purchases / Month": "{:.1f}",
        "Avg per Month": lambda v: m.fmt_aed(v, 2),
        "Projected per Year": lambda v: m.fmt_aed(v, 2),
    })
    st.dataframe(styled, hide_index=True, width="stretch")


def render(df: pd.DataFrame) -> None:
    """Render the Lifestyle tab."""
    if m.purchases(df).empty:
        st.warning("No purchases match the current filters.")
        return

    section("Delivery vs Groceries vs Dining Out", "Monthly spend on ordering in, cooking at home and eating out.")
    st.plotly_chart(charts.food_spend_chart(df), width="stretch")

    left, right = st.columns(2)
    with left:
        section("Coffee Tracker", f"Visits and spend at coffee shops ({', '.join(m.COFFEE_MERCHANTS)}).")
        render_coffee(df)
    with right:
        section("Delivery Orders per Week", "Food delivery orders per Monday-start week; edge weeks may be partial.")
        if m.weekly_delivery_orders(df).empty:
            st.info("No delivery orders in the current selection.")
        else:
            st.plotly_chart(charts.weekly_delivery_chart(df), width="stretch")

    section("What My Habits Cost per Year", "Average monthly spend in the selection × 12; coffee is not double-counted in dining out.")
    render_habit_costs(df)
