"""Patterns tab: weekday rhythm, weekday vs weekend, calendar, ticket sizes, monthly pace."""

import pandas as pd
import streamlit as st

from src import charts
from src import metrics as m
from src.tabs import section


def render_weekday_weekend(df: pd.DataFrame) -> None:
    """Metric cards comparing average daily spend on weekdays and weekends."""
    weekday_avg, weekend_avg = m.weekday_weekend_avg(df)
    delta = None
    if weekday_avg and weekend_avg is not None:
        delta = f"{m.fmt_pct(weekend_avg / weekday_avg - 1, 0, signed=True)} vs weekdays"
    st.metric("Avg Daily Spend · Weekdays", m.fmt_aed(weekday_avg), help="Mon–Fri, including no-spend days")
    st.metric(
        "Avg Daily Spend · Weekends", m.fmt_aed(weekend_avg), delta=delta, delta_color="off",
        help="Sat–Sun (UAE weekend), including no-spend days",
    )


def render(df: pd.DataFrame) -> None:
    """Render the Patterns tab."""
    rows = m.purchases(df)
    if rows.empty:
        st.warning("No purchases match the current filters.")
        return

    left, right = st.columns([3, 1])
    with left:
        section("Day-of-Week Pattern", "Total purchase spend (top) and number of purchases (bottom) by weekday.")
        st.plotly_chart(charts.weekday_pattern_chart(df), width="stretch")
    with right:
        section("Weekday vs Weekend", "Average spend per calendar day.")
        render_weekday_weekend(df)

    section("Spending Calendar", "Daily purchase spend; colour is capped at the 95th percentile, hover for exact amounts.")
    st.plotly_chart(charts.spending_calendar_chart(df), width="stretch")

    cap = rows["amount_aed"].quantile(0.99)
    hidden = int((rows["amount_aed"] > cap).sum())
    left, right = st.columns(2)
    with left:
        section("Ticket Size Distribution", f"Purchase amounts up to the 99th percentile ({m.fmt_aed(cap)}); {hidden} larger purchases not shown.")
        st.plotly_chart(charts.ticket_size_histogram(df), width="stretch")
    with right:
        section("Cumulative Spend Through the Month", "Running purchase total by day of month, one line per month.")
        st.plotly_chart(charts.cumulative_month_chart(df), width="stretch")
