"""Alerts & Explorer tab: transactions worth checking, plus a searchable full list."""

import pandas as pd
import streamlit as st

from src import metrics as m
from src.tabs import section

EXPLORER_COLUMNS = {
    "txn_id": "ID", "txn_date": "Date", "post_date": "Posted", "merchant": "Merchant",
    "category": "Category", "txn_type": "Type", "amount_aed": "Amount (AED)",
    "original_currency": "Currency", "original_amount": "Original Amount",
    "description": "Description",
}


def _show_rows(rows: pd.DataFrame, extra: dict[str, str] | None = None, formats: dict | None = None) -> None:
    """Show a compact, formatted table of transactions plus any extra columns."""
    columns = {"txn_id": "ID", "txn_date": "Date", "merchant": "Merchant",
               "category": "Category", "amount_aed": "Amount", **(extra or {})}
    table = rows[list(columns)].rename(columns=columns)
    styled = table.style.format({"Date": m.fmt_date, "Amount": lambda v: m.fmt_aed(v, 2), **(formats or {})})
    st.dataframe(styled, hide_index=True, width="stretch")


def render_alerts(df: pd.DataFrame) -> None:
    """Three expanders: possible duplicates, large transactions, unusual for merchant."""
    duplicates = df[df["is_duplicate_suspect"]].sort_values(["txn_date", "merchant"])
    large = df[df["is_large"]].sort_values("amount_aed", ascending=False)
    unusual = m.unusual_for_merchant(df)

    with st.expander(f"Possible Duplicates ({len(duplicates)})", expanded=len(duplicates) > 0):
        st.caption("Purchases with the same date, merchant and amount as another purchase.")
        if duplicates.empty:
            st.write("No possible duplicates.")
        else:
            _show_rows(duplicates)

    with st.expander(f"Large Transactions ({len(large)})"):
        st.caption("Purchases above the 95th percentile of all purchase amounts.")
        if large.empty:
            st.write("No large transactions.")
        else:
            _show_rows(large)

    with st.expander(f"Unusual for This Merchant ({len(unusual)})"):
        st.caption("Purchases more than 2 standard deviations above the merchant's average "
                   "(merchants with at least 3 purchases).")
        if unusual.empty:
            st.write("No unusual amounts.")
        else:
            _show_rows(
                unusual,
                extra={"merchant_mean": "Merchant Avg", "times_mean": "× Avg"},
                formats={"Merchant Avg": lambda v: m.fmt_aed(v, 2), "× Avg": "{:.1f}×"},
            )


def render_explorer(df: pd.DataFrame) -> None:
    """Search box, formatted transaction table and CSV download of the current view."""
    query = st.text_input("Search merchant or description", placeholder="e.g. talabat, noon, london")
    view = m.search_transactions(df, query).sort_values(["txn_date", "txn_id"])
    st.caption(f"{len(view):,} of {len(df):,} transactions")

    table = view[list(EXPLORER_COLUMNS)].rename(columns=EXPLORER_COLUMNS)
    styled = table.style.format({
        "Date": m.fmt_date, "Posted": m.fmt_date,
        "Amount (AED)": lambda v: m.fmt_aed(v, 2), "Original Amount": "{:,.2f}",
    })
    st.dataframe(styled, hide_index=True, width="stretch", height=480)

    csv = view.assign(
        txn_date=view["txn_date"].dt.strftime("%Y-%m-%d"),
        post_date=view["post_date"].dt.strftime("%Y-%m-%d"),
    ).to_csv(index=False)
    st.download_button(
        "Download CSV", data=csv, file_name="transactions_view.csv", mime="text/csv",
        icon=":material/download:",
    )


def render(df: pd.DataFrame) -> None:
    """Render the Alerts & Explorer tab."""
    if df.empty:
        st.warning("No transactions match the current filters.")
        return

    section("Alerts", "Transactions worth a second look; open each group to see the rows.")
    render_alerts(df)

    section("All Transactions", "Every transaction in the selection; search, sort by any column, or download the view.")
    render_explorer(df)
