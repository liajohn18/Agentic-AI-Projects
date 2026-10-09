"""Chart functions. Each takes the filtered dataframe and returns a Plotly figure."""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.metrics import (
    WEEKDAYS, coffee_purchases, daily_spend, fee_rows, foreign_purchases_with_fees,
    monthly_net_spend, purchases, weekly_delivery_orders,
)

# Validated categorical palette, always assigned in this slot order.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# One fixed colour per category, used by every chart. The eight largest spend
# categories take the palette in slot order; the smaller ones and the non-spend
# rows use neutral greys.
CATEGORY_COLORS = {
    "Groceries": PALETTE[0],
    "Online Shopping": PALETTE[1],
    "Food Delivery": PALETTE[2],
    "Transport": PALETTE[3],
    "Retail & Fashion": PALETTE[4],
    "Dining & Coffee": PALETTE[5],
    "Utilities & Telecom": PALETTE[6],
    "Travel": PALETTE[7],
    "Health & Fitness": "#6f6e69",
    "Entertainment": "#9d9b94",
    "Subscriptions": "#c3c2b7",
    "Fees": "#52514e",
    "Payments": "#898781",
    "Refunds": "#e1e0d9",
}

# Colours for series that are not a single category.
SPEND_COLOR = PALETTE[0]
PAYMENT_COLOR = CATEGORY_COLORS["Payments"]
FIXED_COLOR, DISCRETIONARY_COLOR = PALETTE[0], PALETTE[1]
AVERAGE_COLOR = "#52514e"
GRID_COLOR = "rgba(137, 135, 129, 0.25)"
# Sequential blue ramp (light -> dark) for magnitude, e.g. the spending calendar.
SEQUENTIAL_BLUES = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

CHART_HEIGHT = 400
TALL_CHART_HEIGHT = 520

NON_SPEND_CATEGORIES = ["Payments", "Fees", "Refunds"]
FOOD_CATEGORIES = ["Food Delivery", "Groceries", "Dining & Coffee"]
UTILITY_MERCHANTS = ["DEWA", "du"]


# --- shared helpers -----------------------------------------------------------

def _month_labels(df: pd.DataFrame) -> dict[str, str]:
    """Map 'YYYY-MM' to display labels like 'Apr 2026'."""
    return df.drop_duplicates("month").set_index("month")["month_name"].to_dict()


def _style(fig: go.Figure, height: int = CHART_HEIGHT) -> go.Figure:
    """Apply shared layout: thin bars, rounded ends, recessive grid, AED value axis."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=30, b=10),
        bargap=0.35,
        barcornerradius=4,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(namelength=-1),
    )
    fig.update_xaxes(title=None, showgrid=False)
    fig.update_yaxes(title=None, tickprefix="AED ", tickformat=",.0f", gridcolor=GRID_COLOR)
    return fig


def _monthly_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Purchase spend per month and value of `column`, in month order."""
    rows = purchases(df)
    monthly = rows.groupby(["month", "month_name", column], as_index=False)["amount_aed"].sum()
    return monthly.sort_values("month")


def _category_totals(df: pd.DataFrame) -> pd.Series:
    """Purchase spend per category, largest first."""
    return purchases(df).groupby("category")["amount_aed"].sum().sort_values(ascending=False)


def _hbar(labels, values, categories, hovertemplate, customdata=None, money=True) -> go.Figure:
    """Horizontal bars in the given order (first at the top), coloured by category."""
    fig = go.Figure(go.Bar(
        x=list(values), y=list(labels), orientation="h",
        marker_color=[CATEGORY_COLORS.get(c) for c in categories],
        customdata=customdata, hovertemplate=hovertemplate,
    ))
    fig = _style(fig)
    fig.update_yaxes(autorange="reversed", tickprefix="", showgrid=False)
    fig.update_xaxes(
        tickprefix="AED " if money else "", tickformat="~s" if money else ",.0f",
        showgrid=True, gridcolor=GRID_COLOR, nticks=5,
    )
    return fig


def _average_line(fig: go.Figure, average: float, label: str) -> None:
    """Add a dashed horizontal reference line for an average."""
    fig.add_hline(
        y=average, line_dash="dash", line_width=2, line_color=AVERAGE_COLOR,
        annotation_text=label, annotation_position="top left",
    )


# --- Overview -------------------------------------------------------------------

def monthly_trend_chart(df: pd.DataFrame) -> go.Figure:
    """Bar chart of net spend per month with a dashed average line."""
    monthly = monthly_net_spend(df)
    fig = go.Figure(go.Bar(
        x=monthly.index.map(_month_labels(df)), y=monthly.values, marker_color=SPEND_COLOR,
        name="Net spend", hovertemplate="%{x}<br><b>AED %{y:,.0f}</b><extra></extra>",
    ))
    if len(monthly):
        _average_line(fig, monthly.mean(), f"Average AED {monthly.mean():,.0f}")
    return _style(fig)


def category_donut(df: pd.DataFrame) -> go.Figure:
    """Donut of spend by category (excludes payments, fees and refunds)."""
    spend = df[~df["category"].isin(NON_SPEND_CATEGORIES)]
    by_category = (
        spend.groupby("category", as_index=False)["amount_aed"].sum()
        .sort_values("amount_aed", ascending=False)
    )
    fig = px.pie(
        by_category, names="category", values="amount_aed", hole=0.6,
        color="category", color_discrete_map=CATEGORY_COLORS,
    )
    fig.update_traces(
        # Labels stay inside the ring; slices too small for one simply show none.
        sort=False, direction="clockwise", textinfo="percent", textposition="inside",
        hovertemplate="%{label}<br><b>AED %{value:,.0f}</b> (%{percent})<extra></extra>",
    )
    fig.update_layout(
        height=CHART_HEIGHT, margin=dict(l=10, r=10, t=30, b=10),
        uniformtext=dict(minsize=11, mode="hide"), legend=dict(title=None),
    )
    return fig


def spend_vs_payments_chart(df: pd.DataFrame) -> go.Figure:
    """Grouped bars per month: purchases vs card payments."""
    labels = _month_labels(df)
    spent = purchases(df).groupby("month")["amount_aed"].sum()
    paid = df[df["txn_type"] == "PAYMENT"].groupby("month")["amount_aed"].sum().abs()
    months = sorted(set(spent.index) | set(paid.index))
    x = [labels[m] for m in months]
    fig = go.Figure([
        go.Bar(x=x, y=spent.reindex(months, fill_value=0), name="Purchases", marker_color=SPEND_COLOR),
        go.Bar(x=x, y=paid.reindex(months, fill_value=0), name="Payments", marker_color=PAYMENT_COLOR),
    ])
    fig.update_traces(hovertemplate="%{fullData.name}: <b>AED %{y:,.0f}</b><extra></extra>")
    fig.update_layout(barmode="group", bargroupgap=0.08, hovermode="x unified")
    return _style(fig)


# --- Categories -----------------------------------------------------------------

def category_ranking_chart(df: pd.DataFrame) -> go.Figure:
    """Horizontal bars of purchase spend by category, largest at the top."""
    totals = _category_totals(df)
    return _hbar(
        totals.index, totals.values, totals.index,
        "%{y}<br><b>AED %{x:,.0f}</b> (%{customdata:.1%})<extra></extra>",
        customdata=(totals / totals.sum()).values,
    )


def category_mix_chart(df: pd.DataFrame) -> go.Figure:
    """Stacked bars of purchase spend per month, split by category."""
    fig = px.bar(
        _monthly_by(df, "category"), x="month_name", y="amount_aed", color="category",
        color_discrete_map=CATEGORY_COLORS,
        category_orders={"category": list(_category_totals(df).index)},
        custom_data=["category"],
    )
    fig.update_traces(hovertemplate="%{customdata[0]}: <b>AED %{y:,.0f}</b><extra></extra>")
    fig.update_layout(barmode="stack", hovermode="x unified")
    fig = _style(fig)
    # Rounded ends would round every stacked segment, so keep them square here.
    fig.update_layout(barcornerradius=0)
    return fig


def category_treemap(df: pd.DataFrame) -> go.Figure:
    """Treemap of purchase spend: category, then merchant."""
    by_merchant = purchases(df).groupby(["category", "merchant"], as_index=False)["amount_aed"].sum()
    fig = px.treemap(
        by_merchant, path=["category", "merchant"], values="amount_aed",
        color="category", color_discrete_map=CATEGORY_COLORS,
    )
    fig.update_traces(
        root_color="rgba(0,0,0,0)",
        texttemplate="%{label}<br>AED %{value:,.0f}",
        hovertemplate="%{label}<br><b>AED %{value:,.0f}</b><br>%{percentParent:.1%} of %{parent}<extra></extra>",
        marker=dict(line=dict(width=2)),
    )
    fig.update_layout(height=TALL_CHART_HEIGHT, margin=dict(l=10, r=10, t=30, b=10))
    return fig


# --- Merchants ------------------------------------------------------------------

def top_merchants_by_spend_chart(stats: pd.DataFrame, n: int = 10) -> go.Figure:
    """Top n merchants by purchase spend, coloured by category."""
    top = stats.nlargest(n, "spend")
    return _hbar(
        top["merchant"], top["spend"], top["category"],
        "%{y}<br><b>AED %{x:,.0f}</b><br>%{customdata}<extra></extra>",
        customdata=top["category"],
    )


def top_merchants_by_count_chart(stats: pd.DataFrame, n: int = 10) -> go.Figure:
    """Top n merchants by number of purchases, coloured by category."""
    top = stats.nlargest(n, "transactions")
    return _hbar(
        top["merchant"], top["transactions"], top["category"],
        "%{y}<br><b>%{x} transactions</b><br>%{customdata[0]} · AED %{customdata[1]:,.0f}<extra></extra>",
        customdata=top[["category", "spend"]].values, money=False,
    )


def frequency_vs_ticket_chart(stats: pd.DataFrame) -> go.Figure:
    """Bubble scatter: transactions vs average ticket, sized by spend (log axes)."""
    fig = px.scatter(
        stats, x="transactions", y="avg_ticket", size="spend", color="category",
        color_discrete_map=CATEGORY_COLORS, log_x=True, log_y=True, size_max=45,
        custom_data=["merchant", "category", "spend"],
    )
    fig.update_traces(
        marker=dict(opacity=0.8, line=dict(width=2, color="rgba(252,252,251,0.9)")),
        hovertemplate=(
            "<b>%{customdata[0]}</b> · %{customdata[1]}<br>%{x} transactions"
            "<br>Avg ticket AED %{y:,.2f}<br>Total AED %{customdata[2]:,.0f}<extra></extra>"
        ),
    )
    fig = _style(fig, height=TALL_CHART_HEIGHT)
    # dtick=1 labels only powers of ten, so every tick carries its prefix.
    fig.update_xaxes(title="Transactions (log scale)", showgrid=True, gridcolor=GRID_COLOR, dtick=1)
    fig.update_yaxes(title="Average ticket (log scale)", dtick=1)
    return fig


# --- Patterns -------------------------------------------------------------------

def weekday_pattern_chart(df: pd.DataFrame) -> go.Figure:
    """Two stacked panels sharing a Mon→Sun axis: total spend (bars) and transaction count (line)."""
    by_day = purchases(df).groupby("weekday")["amount_aed"].agg(["sum", "count"]).reindex(WEEKDAYS)
    labels = [d[:3] for d in WEEKDAYS]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14, row_heights=[0.6, 0.4],
        subplot_titles=("Total spend", "Transactions"),
    )
    fig.add_trace(go.Bar(
        x=labels, y=by_day["sum"], marker_color=SPEND_COLOR, name="Spend",
        hovertemplate="%{x}<br><b>AED %{y:,.0f}</b><extra></extra>",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=labels, y=by_day["count"], mode="lines+markers", name="Transactions",
        line=dict(color=AVERAGE_COLOR, width=2), marker=dict(size=8),
        hovertemplate="%{x}<br><b>%{y} transactions</b><extra></extra>",
    ), row=2, col=1)
    fig = _style(fig)
    fig.update_layout(showlegend=False)
    fig.update_yaxes(tickprefix="", row=2, col=1)
    fig.update_yaxes(rangemode="tozero")
    return fig


def spending_calendar_chart(df: pd.DataFrame) -> go.Figure:
    """Heatmap of daily purchase spend: month (rows) × day of month (columns)."""
    daily = daily_spend(df).to_frame("spend")
    daily["month"] = daily.index.strftime("%b %Y")
    daily["month_key"] = daily.index.strftime("%Y-%m")
    daily["day"] = daily.index.day
    grid = daily.pivot_table(index=["month_key", "month"], columns="day", values="spend")
    grid = grid.reindex(columns=range(1, 32))
    # Cap the colour scale so one big-ticket day doesn't wash out the rest.
    zmax = float(daily["spend"].quantile(0.95)) or None
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=list(grid.columns), y=grid.index.get_level_values("month"),
        colorscale=[[i / (len(SEQUENTIAL_BLUES) - 1), c] for i, c in enumerate(SEQUENTIAL_BLUES)],
        zmin=0, zmax=zmax, xgap=2, ygap=2, hoverongaps=False,
        colorbar=dict(tickprefix="AED ", tickformat=",.0f", thickness=12),
        hovertemplate="%{y}, day %{x}<br><b>AED %{z:,.0f}</b><extra></extra>",
    ))
    fig = _style(fig)
    fig.update_xaxes(dtick=1, title="Day of month")
    fig.update_yaxes(tickprefix="", autorange="reversed", showgrid=False)
    return fig


def ticket_size_histogram(df: pd.DataFrame, bins: int = 40) -> go.Figure:
    """Histogram of purchase amounts, x-axis capped at the 99th percentile."""
    amounts = purchases(df)["amount_aed"]
    cap = float(amounts.quantile(0.99))
    counts, edges = np.histogram(amounts[amounts <= cap], bins=bins, range=(0, cap))
    fig = go.Figure(go.Bar(
        x=(edges[:-1] + edges[1:]) / 2, y=counts, width=np.diff(edges) * 0.92,
        marker_color=SPEND_COLOR, customdata=np.column_stack([edges[:-1], edges[1:]]),
        hovertemplate="AED %{customdata[0]:,.0f}–%{customdata[1]:,.0f}<br><b>%{y} purchases</b><extra></extra>",
    ))
    fig = _style(fig)
    fig.update_layout(barcornerradius=2)
    fig.update_xaxes(tickprefix="AED ", tickformat=",.0f", range=[0, cap])
    fig.update_yaxes(tickprefix="", title="Purchases")
    return fig


def cumulative_month_chart(df: pd.DataFrame) -> go.Figure:
    """One line per month: running purchase spend by day of month."""
    daily = purchases(df).groupby(["month", "month_name", "day_of_month"])["amount_aed"].sum()
    fig = go.Figure()
    for i, ((month, name), series) in enumerate(daily.groupby(level=[0, 1])):
        days_in_month = pd.Period(month).days_in_month
        running = series.droplevel([0, 1]).reindex(range(1, days_in_month + 1), fill_value=0).cumsum()
        fig.add_trace(go.Scatter(
            x=running.index, y=running.values, mode="lines", name=name,
            line=dict(color=PALETTE[i % len(PALETTE)], width=2),
            hovertemplate=f"{name}: <b>AED %{{y:,.0f}}</b><extra></extra>",
        ))
    fig = _style(fig)
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title="Day of month", dtick=5, showgrid=True, gridcolor=GRID_COLOR)
    return fig


# --- Recurring ------------------------------------------------------------------

def fixed_vs_discretionary_chart(df: pd.DataFrame) -> go.Figure:
    """Stacked bars per month: recurring (fixed) vs all other purchases."""
    kinds = purchases(df).assign(kind=lambda d: d["is_recurring"].map({True: "Fixed", False: "Discretionary"}))
    fig = px.bar(
        _monthly_by(kinds, "kind"), x="month_name", y="amount_aed", color="kind",
        color_discrete_map={"Fixed": FIXED_COLOR, "Discretionary": DISCRETIONARY_COLOR},
        category_orders={"kind": ["Fixed", "Discretionary"]}, custom_data=["kind"],
    )
    fig.update_traces(hovertemplate="%{customdata[0]}: <b>AED %{y:,.0f}</b><extra></extra>")
    fig.update_layout(barmode="stack", hovermode="x unified")
    fig = _style(fig)
    fig.update_layout(barcornerradius=0)
    return fig


def utility_bills_chart(df: pd.DataFrame) -> go.Figure:
    """Line per utility merchant (DEWA, du) showing its monthly bill."""
    monthly = _monthly_by(df[df["merchant"].isin(UTILITY_MERCHANTS)], "merchant")
    fig = go.Figure()
    for i, merchant in enumerate(UTILITY_MERCHANTS):
        line = monthly[monthly["merchant"] == merchant]
        if line.empty:
            continue
        fig.add_trace(go.Scatter(
            x=line["month_name"], y=line["amount_aed"], mode="lines+markers", name=merchant,
            line=dict(color=PALETTE[i], width=2), marker=dict(size=8),
            hovertemplate=f"{merchant}: <b>AED %{{y:,.0f}}</b><extra></extra>",
        ))
    fig = _style(fig)
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(rangemode="tozero")
    return fig


# --- Lifestyle ------------------------------------------------------------------

def food_spend_chart(df: pd.DataFrame) -> go.Figure:
    """Grouped bars per month for Food Delivery, Groceries and Dining & Coffee."""
    fig = px.bar(
        _monthly_by(df[df["category"].isin(FOOD_CATEGORIES)], "category"),
        x="month_name", y="amount_aed", color="category", barmode="group",
        color_discrete_map=CATEGORY_COLORS, category_orders={"category": FOOD_CATEGORIES},
        custom_data=["category"],
    )
    fig.update_traces(hovertemplate="%{customdata[0]}: <b>AED %{y:,.0f}</b><extra></extra>")
    fig.update_layout(bargroupgap=0.08, hovermode="x unified")
    return _style(fig)


def coffee_monthly_chart(df: pd.DataFrame) -> go.Figure:
    """Monthly coffee spend bars, with visit count in the tooltip."""
    monthly = coffee_purchases(df).groupby(["month", "month_name"])["amount_aed"].agg(["sum", "count"])
    monthly = monthly.reset_index().sort_values("month")
    fig = go.Figure(go.Bar(
        x=monthly["month_name"], y=monthly["sum"], marker_color=CATEGORY_COLORS["Dining & Coffee"],
        customdata=monthly["count"], name="Coffee",
        hovertemplate="%{x}<br><b>AED %{y:,.0f}</b><br>%{customdata} visits<extra></extra>",
    ))
    return _style(fig)


def weekly_delivery_chart(df: pd.DataFrame) -> go.Figure:
    """Line of Food Delivery orders per week, with a dashed weekly average."""
    weekly = weekly_delivery_orders(df)
    fig = go.Figure(go.Scatter(
        x=weekly.index, y=weekly.values, mode="lines+markers", name="Orders",
        line=dict(color=CATEGORY_COLORS["Food Delivery"], width=2), marker=dict(size=8),
        hovertemplate="Week of %{x|%d %b}<br><b>%{y} orders</b><extra></extra>",
    ))
    if len(weekly):
        _average_line(fig, weekly.mean(), f"Average {weekly.mean():.1f} / week")
    fig = _style(fig)
    fig.update_yaxes(tickprefix="", rangemode="tozero")
    fig.update_xaxes(tickformat="%d %b")
    return fig


# --- Travel & Fees --------------------------------------------------------------

def london_trip_chart(df: pd.DataFrame) -> go.Figure:
    """Horizontal bars of each foreign purchase in AED (date order), GBP and FX fee in the tooltip."""
    foreign = foreign_purchases_with_fees(df)
    labels = foreign["txn_date"].dt.strftime("%d %b") + " · " + foreign["merchant"]
    return _hbar(
        labels, foreign["amount_aed"], ["Travel"] * len(foreign),
        "%{y}<br><b>AED %{x:,.2f}</b><br>GBP %{customdata[0]:,.2f}"
        "<br>FX fee AED %{customdata[1]:,.2f}<extra></extra>",
        customdata=foreign[["original_amount", "fx_fee"]].values,
    )


def card_fees_chart(df: pd.DataFrame) -> go.Figure:
    """Horizontal bars of every FEE row, largest first."""
    fees = fee_rows(df).sort_values("amount_aed", ascending=False)
    labels = fees["description"].str.title().str.replace("Foreign Transaction Fee", "FX fee", regex=False)
    return _hbar(
        labels, fees["amount_aed"], ["Fees"] * len(fees),
        "%{y}<br><b>AED %{x:,.2f}</b><br>%{customdata}<extra></extra>",
        customdata=fees["txn_date"].dt.strftime("%d %b %Y"),
    )
