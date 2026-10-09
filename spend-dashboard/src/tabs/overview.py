"""Overview tab: headline KPIs, monthly trend, category split and insights."""

import pandas as pd
import streamlit as st

from src import charts, chat
from src import metrics as m
from src.tabs import section

CHAT_KEY = "chat_history"


def render_key_metrics(df: pd.DataFrame) -> None:
    """Two rows of st.metric cards."""
    mom = m.mom_change(df)
    top = m.top_category(df)

    row1 = st.columns(4)
    row1[0].metric(
        "Total Spend", m.fmt_aed(m.total_net_spend(df)),
        delta=None if mom is None else f"{m.fmt_pct(mom, signed=True)} vs prev. month",
        delta_color="inverse", help="Purchases plus refunds",
    )
    row1[1].metric("Avg Monthly Spend", m.fmt_aed(m.avg_monthly_spend(df)))
    row1[2].metric("Transactions", f"{m.txn_count(df):,}", help="Number of purchases")
    row1[3].metric("Avg Transaction", m.fmt_aed(m.avg_txn_value(df)))

    row2 = st.columns(4)
    row2[0].metric(
        "Top Category", "—" if top is None else f"{top[0]} · {m.fmt_pct(top[1], 0)}",
        help="Largest category by purchase spend and its share",
    )
    row2[1].metric(
        "Monthly Commitments", m.fmt_aed(m.monthly_commitments(df)),
        help="Average monthly spend on recurring purchases (subscriptions and bills)",
    )
    row2[2].metric("Delivery Share", m.fmt_pct(m.delivery_share(df)), help="Food Delivery ÷ purchases")
    row2[3].metric("Fees Paid", m.fmt_aed(m.total_fees(df)))


def highest_month_insight(df: pd.DataFrame) -> str | None:
    """Sentence naming the highest-spend month and the category that drove it."""
    monthly = m.monthly_net_spend(df)
    if len(monthly) < 2:
        return None
    month = monthly.idxmax()
    label = df.loc[df["month"] == month, "month_name"].iloc[0]
    above = monthly[month] / monthly.mean() - 1

    spend = df[df["txn_type"].isin(["PURCHASE", "REFUND"])]
    by_cat = spend.pivot_table(
        index="month", columns="category", values="amount_aed", aggfunc="sum", fill_value=0,
    )
    driver = (by_cat.loc[month] - by_cat.mean()).idxmax()
    extra = by_cat.loc[month, driver] - by_cat[driver].mean()
    return (
        f"**{label}** was the highest month at **{m.fmt_aed(monthly[month])}**, "
        f"{m.fmt_pct(above, 0)} above the monthly average, driven mainly by **{driver}** "
        f"({m.fmt_aed(extra)} more than a typical month)."
    )


def top_category_insight(df: pd.DataFrame) -> str | None:
    """Sentence on the top category's share of purchase spend."""
    top = m.top_category(df)
    if top is None:
        return None
    category, share = top
    rows = m.purchases(df)
    amount = rows.loc[rows["category"] == category, "amount_aed"].sum()
    return (
        f"**{category}** is the largest category at **{m.fmt_aed(amount)}**, "
        f"{m.fmt_pct(share, 0)} of all purchase spend."
    )


def payment_coverage_insight(df: pd.DataFrame) -> str | None:
    """Sentence on how much of the purchase spend has been paid off."""
    coverage = m.payment_coverage(df)
    if coverage is None:
        return None
    spent = m.purchases(df)["amount_aed"].sum()
    paid = abs(df.loc[df["txn_type"] == "PAYMENT", "amount_aed"].sum())
    note = "fully covered" if coverage >= 1 else f"leaving about {m.fmt_aed(spent - paid)} unpaid"
    return (
        f"Card payments of **{m.fmt_aed(paid)}** cover **{m.fmt_pct(coverage, 0)}** of purchases "
        f"({m.fmt_aed(spent)}), {note}."
    )


def render_insights(df: pd.DataFrame) -> None:
    """Bullet list of auto-generated insight sentences."""
    insights = [highest_month_insight(df), top_category_insight(df), payment_coverage_insight(df)]
    lines = [f"- {text}" for text in insights if text]
    st.markdown("\n".join(lines) if lines else "Not enough data for insights.")


def _ask(question: str, df: pd.DataFrame) -> None:
    """Add a question and its answer to the chat history."""
    history = st.session_state.setdefault(CHAT_KEY, [])
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": chat.answer(question, df)})


def _clear_chat() -> None:
    """Callback for the clear button: empty the chat history."""
    st.session_state[CHAT_KEY] = []


def render_chat(df: pd.DataFrame) -> None:
    """Chat window: an input box, plus the conversation and a clear button once something is asked."""
    # Reserve the space above the input first, then fill it once the new question is answered.
    messages = st.container()
    question = st.chat_input("Ask a question about your spending")
    if question:
        _ask(question, df)

    history = st.session_state.get(CHAT_KEY, [])
    if not history:
        return
    with messages, st.container(border=True, height=420):
        for message in history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    st.button("Clear chat", on_click=_clear_chat)


def render(df: pd.DataFrame) -> None:
    """Render the Overview tab."""
    if df.empty:
        st.warning("No transactions match the current filters.")
        return

    section("Key Metrics", "Headline numbers for the selection; spend is purchases plus refunds, never card payments.")
    render_key_metrics(df)

    left, right = st.columns([3, 2])
    with left:
        section("Monthly Spend Trend", "Net spend per month; the dashed line is the monthly average.")
        st.plotly_chart(charts.monthly_trend_chart(df), width="stretch")
    with right:
        section("Where the Money Goes", "Share of spend by category, excluding payments, fees and refunds.")
        st.plotly_chart(charts.category_donut(df), width="stretch")

    left, right = st.columns([3, 2])
    with left:
        section("Spend vs Payments", "Purchases charged to the card vs bill payments made, per month.")
        st.plotly_chart(charts.spend_vs_payments_chart(df), width="stretch")
    with right:
        section("Key Insights", "Auto-generated from the current filters.")
        render_insights(df)

    section(
        "AI Analyst",
        "Ask in plain English; answers are calculated from the data in the current filters "
        "and nothing leaves your computer.",
    )
    render_chat(df)
