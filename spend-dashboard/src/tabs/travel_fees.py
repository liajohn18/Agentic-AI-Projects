"""Travel & Fees tab: foreign spend, London trip, card fees and refunds."""

import pandas as pd
import streamlit as st

from src import charts
from src import metrics as m
from src.tabs import section


def _fmt_gbp(value: float, decimals: int = 2) -> str:
    """Format a number as 'GBP 1,234.00'."""
    return f"GBP {value:,.{decimals}f}"


def render_fx_summary(df: pd.DataFrame) -> None:
    """Metric cards for foreign spend and FX fees."""
    fx = m.fx_summary(df)
    cols = st.columns(4)
    cols[0].metric("Total GBP Spent", _fmt_gbp(fx["original"], 0))
    cols[1].metric("AED Equivalent", m.fmt_aed(fx["aed"]))
    cols[2].metric("FX Fees Paid", m.fmt_aed(fx["fees"]))
    cols[3].metric(
        "Effective FX Cost", m.fmt_pct(fx["effective_cost"], 2),
        help="Foreign transaction fees ÷ AED value of foreign purchases",
    )


def render_london_trip(df: pd.DataFrame) -> None:
    """Table and bar chart of foreign (GBP) purchases with their matched fees."""
    foreign = m.foreign_purchases_with_fees(df)
    if foreign.empty:
        st.info("No foreign transactions in the current selection.")
        return
    table = foreign[["txn_date", "merchant", "original_amount", "amount_aed", "rate", "fx_fee"]].rename(columns={
        "txn_date": "Date", "merchant": "Merchant", "original_amount": "GBP",
        "amount_aed": "AED", "rate": "AED per GBP", "fx_fee": "FX Fee",
    })
    styled = table.style.format({
        "Date": m.fmt_date, "GBP": _fmt_gbp, "AED": lambda v: m.fmt_aed(v, 2),
        "AED per GBP": "{:.3f}", "FX Fee": lambda v: m.fmt_aed(v, 2),
    })
    left, right = st.columns([3, 2])
    with left:
        st.dataframe(styled, hide_index=True, width="stretch")
    with right:
        st.plotly_chart(charts.london_trip_chart(df), width="stretch")


def render_card_fees(df: pd.DataFrame) -> None:
    """Table and bar chart of every FEE row."""
    fees = m.fee_rows(df)
    if fees.empty:
        st.info("No card fees in the current selection.")
        return
    table = fees.sort_values("txn_date")[["txn_date", "description", "amount_aed"]].rename(columns={
        "txn_date": "Date", "description": "Description", "amount_aed": "Amount",
    })
    styled = table.style.format({"Date": m.fmt_date, "Amount": lambda v: m.fmt_aed(v, 2)})
    left, right = st.columns([3, 2])
    with left:
        st.dataframe(styled, hide_index=True, width="stretch")
    with right:
        st.plotly_chart(charts.card_fees_chart(df), width="stretch")


def render_refunds(df: pd.DataFrame) -> None:
    """Table of refund rows."""
    refunds = df[df["txn_type"] == "REFUND"].sort_values("txn_date")
    if refunds.empty:
        st.info("No refunds in the current selection.")
        return
    table = refunds[["txn_date", "post_date", "merchant", "description", "amount_aed"]].rename(columns={
        "txn_date": "Date", "post_date": "Posted", "merchant": "Merchant",
        "description": "Description", "amount_aed": "Amount",
    })
    styled = table.style.format({"Date": m.fmt_date, "Posted": m.fmt_date, "Amount": lambda v: m.fmt_aed(v, 2)})
    st.dataframe(styled, hide_index=True, width="stretch")


def render(df: pd.DataFrame) -> None:
    """Render the Travel & Fees tab."""
    if df.empty:
        st.warning("No transactions match the current filters.")
        return
    fees_total = m.fmt_aed(m.total_fees(df), 2)
    refunds_total = m.fmt_aed(abs(df.loc[df["txn_type"] == "REFUND", "amount_aed"].sum()), 2)

    section("Foreign Spend Summary", "Spending in foreign currency and what the card charged to convert it.")
    render_fx_summary(df)

    section("London Trip Breakdown", "Each GBP purchase with its AED value, exchange rate and matched foreign transaction fee.")
    render_london_trip(df)

    section("Card Fees", f"Every fee charged to the card: the annual fee plus foreign transaction fees ({fees_total} in total).")
    render_card_fees(df)

    section("Refunds", f"Money returned to the card by merchants ({refunds_total} in total).")
    render_refunds(df)
