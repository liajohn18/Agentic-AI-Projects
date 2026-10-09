"""Rule-based Q&A over the transactions: no AI, no API key, answers come from metrics.py.

answer(question, df) recognises the kind of question (total, count, top merchants, ...)
and any merchant, category or month mentioned in it, then returns a markdown reply.
"""

import re

import pandas as pd

from src import metrics as m

EXAMPLES = [
    "How much did I spend at Talabat?",
    "Groceries in June",
    "Top 5 merchants",
    "Biggest purchases",
    "Compare July and August",
    "How many times did I buy coffee?",
]

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# Words that point at a category. Longer phrases are checked first.
CATEGORY_WORDS = {
    "Groceries": ["groceries", "grocery", "supermarket", "supermarkets"],
    "Online Shopping": ["online shopping", "online"],
    "Food Delivery": ["food delivery", "delivery", "deliveries", "takeaway", "takeaways"],
    "Dining & Coffee": ["dining", "eating out", "restaurant", "restaurants"],
    "Transport": ["transport", "taxi", "taxis", "rides", "fuel", "petrol"],
    "Retail & Fashion": ["retail", "fashion", "clothes", "clothing"],
    "Utilities & Telecom": ["utilities", "utility", "telecom", "bills"],
    "Subscriptions": ["subscriptions", "subscription", "streaming"],
    "Health & Fitness": ["health", "gym", "pharmacy"],
    "Entertainment": ["entertainment", "cinema", "movies"],
    "Travel": ["travel", "london", "trip", "holiday"],
}

# Extra names people use for merchants, on top of the merchant name and its first word.
MERCHANT_ALIASES = {"cheesecake": "The Cheesecake Factory", "hortons": "Tim Hortons", "icloud": "Apple iCloud"}

HELP = (
    "I answer questions straight from the dashboard data (current sidebar filters). Try:\n"
    + "\n".join(f"- *{q}*" for q in EXAMPLES)
    + "\n- *Average transaction at Careem*\n- *Which month did I spend the most?*"
    "\n- *Total fees* · *Refunds* · *Payments* · *Recurring bills* · *Duplicates* · *Weekend spending*"
)


# --- parsing --------------------------------------------------------------------

def _has_word(text: str, phrase: str) -> bool:
    """True if phrase appears in text as whole word(s)."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _has_any(text: str, *phrases: str) -> bool:
    """True if any phrase appears in text as whole word(s)."""
    return any(_has_word(text, p) for p in phrases)


def find_months(text: str) -> list[int]:
    """Month numbers mentioned in the text, in calendar order."""
    return sorted({num for word, num in MONTHS.items() if _has_word(text, word)})


def _month_name(number: int, df: pd.DataFrame) -> str:
    """'Jun 2026' for month number 6, using the latest year in the data."""
    year = int(df["txn_date"].dt.year.max()) if not df.empty else pd.Timestamp.today().year
    return pd.Timestamp(year, number, 1).strftime("%b %Y")


def _merchant_aliases(merchants) -> dict[str, str]:
    """Map lower-case names a person might type to the merchant name."""
    aliases = dict(MERCHANT_ALIASES)
    for name in merchants:
        clean = name.lower().replace("%", "").replace(".com", "")
        aliases[clean] = name
        first = clean.split()[0]
        if len(first) >= 3 and first != "the":
            aliases.setdefault(first, name)
    return aliases


def find_merchant(text: str, rows: pd.DataFrame) -> str | None:
    """Merchant mentioned in the text (longest alias wins), or None."""
    aliases = _merchant_aliases(rows["merchant"].unique())
    for alias in sorted(aliases, key=len, reverse=True):
        if _has_word(text, alias) and aliases[alias] in set(rows["merchant"]):
            return aliases[alias]
    return None


def find_category(text: str) -> str | None:
    """Category mentioned in the text (by name or a common word for it), or None."""
    phrases = [(p, cat) for cat, words in CATEGORY_WORDS.items() for p in [cat.lower(), *words]]
    for phrase, category in sorted(phrases, key=lambda pc: len(pc[0]), reverse=True):
        if _has_word(text, phrase):
            return category
    return None


def _scope(text: str, df: pd.DataFrame, use_months: bool = True) -> tuple[pd.DataFrame, str]:
    """Purchases the question is about, plus a phrase describing them ('at Talabat in Jun 2026')."""
    rows = m.purchases(df)
    label = ""
    merchant = find_merchant(text, rows)
    if _has_any(text, "coffee", "coffees"):
        rows, label = m.coffee_purchases(df), "on coffee"
    elif merchant:
        rows, label = rows[rows["merchant"] == merchant], f"at {merchant}"
    elif category := find_category(text):
        rows, label = rows[rows["category"] == category], f"on {category}"
    months = find_months(text) if use_months else []
    if months:
        rows = rows[rows["txn_date"].dt.month.isin(months)]
        label = f"{label} in {' and '.join(_month_name(n, df) for n in months)}".strip()
    # Leading space so templates can write f"purchases{label}" with or without a scope.
    return rows, f" {label}" if label else ""


def _top_n(text: str, default: int = 5) -> int:
    """Number asked for in 'top 3 ...', else the default."""
    match = re.search(r"\b(\d{1,2})\b", text)
    return int(match.group(1)) if match else default


# --- answers --------------------------------------------------------------------

def _no_data(label: str) -> str:
    """Reply when nothing matches."""
    return f"I found no purchases{label} in the current selection."


def answer_total(rows: pd.DataFrame, label: str, df: pd.DataFrame) -> str:
    """Total spend, count and share for the scope, with a monthly breakdown."""
    if rows.empty:
        return _no_data(label)
    total = rows["amount_aed"].sum()
    share = total / m.purchases(df)["amount_aed"].sum()
    reply = f"You spent **{m.fmt_aed(total, 2)}**{label} across **{len(rows)}** purchases"
    reply += f" ({m.fmt_pct(share)} of all purchases in this selection)." if label else "."
    by_month = rows.groupby(["month", "month_name"])["amount_aed"].sum()
    if len(by_month) > 1:
        reply += "\n\nBy month: " + " · ".join(f"{name} {m.fmt_aed(v)}" for (_, name), v in by_month.items())
    return reply


def answer_count(rows: pd.DataFrame, label: str, df: pd.DataFrame) -> str:
    """Number of purchases in the scope and how often that is."""
    if rows.empty:
        return _no_data(label)
    weeks = ((df["txn_date"].max() - df["txn_date"].min()).days + 1) / 7
    return (
        f"You made **{len(rows)}** purchases{label} "
        f"(about {len(rows) / weeks:.1f} a week), totalling {m.fmt_aed(rows['amount_aed'].sum(), 2)}."
    )


def answer_average(rows: pd.DataFrame, label: str, df: pd.DataFrame) -> str:
    """Average ticket and average per month for the scope."""
    if rows.empty:
        return _no_data(label)
    per_month = rows["amount_aed"].sum() / df["month"].nunique()
    return (
        f"The average purchase{label} is **{m.fmt_aed(rows['amount_aed'].mean(), 2)}** "
        f"over {len(rows)} purchases, about {m.fmt_aed(per_month)} per month."
    )


def answer_biggest(rows: pd.DataFrame, label: str, n: int) -> str:
    """The n largest purchases in the scope."""
    if rows.empty:
        return _no_data(label)
    top = rows.nlargest(n, "amount_aed")
    lines = [f"- {m.fmt_date(r.txn_date)} · {r.merchant} · **{m.fmt_aed(r.amount_aed, 2)}**" for r in top.itertuples()]
    return f"Largest purchases{label}:\n" + "\n".join(lines)


def answer_top(rows: pd.DataFrame, label: str, by: str, n: int) -> str:
    """Top n merchants or categories by spend in the scope."""
    if rows.empty:
        return _no_data(label)
    totals = rows.groupby(by)["amount_aed"].agg(["sum", "count"]).nlargest(n, "sum")
    noun = "merchants" if by == "merchant" else "categories"
    lines = [f"{i}. {name} · **{m.fmt_aed(r['sum'])}** ({int(r['count'])} purchases)"
             for i, (name, r) in enumerate(totals.iterrows(), start=1)]
    return f"Top {len(totals)} {noun}{label}:\n" + "\n".join(lines)


def answer_months(rows: pd.DataFrame, label: str) -> str:
    """Months ranked by spend in the scope."""
    if rows.empty:
        return _no_data(label)
    by_month = rows.groupby(["month", "month_name"])["amount_aed"].sum().sort_values(ascending=False)
    (_, top_name), top_value = by_month.index[0], by_month.iloc[0]
    lines = [f"- {name}: {m.fmt_aed(v)}" for (_, name), v in by_month.items()]
    return (
        f"Your highest month for purchases{label} was **{top_name}** at **{m.fmt_aed(top_value)}** "
        "(purchases only, before refunds).\n\n" + "\n".join(lines)
    )


def answer_compare(rows: pd.DataFrame, label: str, months: list[int], df: pd.DataFrame) -> str:
    """Spend in two or more months side by side, with the change between the last two."""
    spend = {n: rows.loc[rows["txn_date"].dt.month == n, "amount_aed"].sum() for n in months}
    names = {n: _month_name(n, df) for n in months}
    lines = [f"- {names[n]}: **{m.fmt_aed(v)}**" for n, v in spend.items()]
    before, after = spend[months[-2]], spend[months[-1]]
    change = f"{m.fmt_pct((after - before) / before, signed=True)} " if before else ""
    header = f"Purchases{label}:"
    return (
        header + "\n" + "\n".join(lines)
        + f"\n\n{names[months[-1]]} was {change}({m.fmt_aed(after - before)}) vs {names[months[-2]]}."
    )


def answer_fees(df: pd.DataFrame) -> str:
    """Total card fees, split into annual and foreign transaction fees."""
    fees = m.fee_rows(df)
    if fees.empty:
        return "There are no card fees in the current selection."
    fx = fees[fees["description"].str.startswith(m.FX_FEE_PREFIX)]["amount_aed"].sum()
    return (
        f"You paid **{m.fmt_aed(fees['amount_aed'].sum(), 2)}** in card fees ({len(fees)} charges): "
        f"{m.fmt_aed(fx, 2)} in foreign transaction fees and "
        f"{m.fmt_aed(fees['amount_aed'].sum() - fx, 2)} in other fees (the annual card fee)."
    )


def answer_payments(df: pd.DataFrame) -> str:
    """Card bill payments and how much of the purchases they cover."""
    payments = df[df["txn_type"] == "PAYMENT"]
    if payments.empty:
        return "There are no card payments in the current selection."
    coverage = m.payment_coverage(df)
    return (
        f"You made **{len(payments)}** card payments totalling **{m.fmt_aed(abs(payments['amount_aed'].sum()), 2)}**, "
        f"covering {m.fmt_pct(coverage, 0)} of purchases in this selection."
    )


def answer_refunds(df: pd.DataFrame) -> str:
    """List of refunds."""
    refunds = df[df["txn_type"] == "REFUND"]
    if refunds.empty:
        return "There are no refunds in the current selection."
    lines = [f"- {m.fmt_date(r.txn_date)} · {r.merchant} · {m.fmt_aed(abs(r.amount_aed), 2)}" for r in refunds.itertuples()]
    return f"You received **{len(refunds)}** refunds totalling **{m.fmt_aed(abs(refunds['amount_aed'].sum()), 2)}**:\n" + "\n".join(lines)


def answer_recurring(df: pd.DataFrame) -> str:
    """Recurring merchants and the monthly commitment."""
    summary = m.recurring_summary(df)
    if summary.empty:
        return "There are no recurring charges in the current selection."
    lines = [f"- {r.merchant}: {m.fmt_aed(r.avg_amount, 2)} a month" for r in summary.itertuples()]
    return (
        f"Your recurring commitments average **{m.fmt_aed(m.monthly_commitments(df))}** a month "
        f"({m.fmt_aed(m.monthly_commitments(df) * 12)} a year):\n" + "\n".join(lines)
    )


def answer_duplicates(df: pd.DataFrame) -> str:
    """Possible duplicate charges."""
    dups = df[df["is_duplicate_suspect"]]
    if dups.empty:
        return "I found no possible duplicate charges in the current selection."
    lines = [f"- {r.txn_id} · {m.fmt_date(r.txn_date)} · {r.merchant} · {m.fmt_aed(r.amount_aed, 2)}" for r in dups.itertuples()]
    return "These purchases share the same date, merchant and amount, so check whether one is a duplicate:\n" + "\n".join(lines)


def answer_weekend(df: pd.DataFrame) -> str:
    """Average daily spend on weekdays vs weekends."""
    weekday, weekend = m.weekday_weekend_avg(df)
    if not weekday or weekend is None:
        return "There isn't enough data to compare weekdays and weekends."
    return (
        f"On average you spend **{m.fmt_aed(weekend)}** a day at weekends (Sat–Sun) vs "
        f"**{m.fmt_aed(weekday)}** on weekdays, {m.fmt_pct(weekend / weekday - 1, 0, signed=True)}."
    )


def answer(question: str, df: pd.DataFrame) -> str:
    """Return a markdown answer to a free-text question about the dashboard data."""
    text = question.lower().strip()
    if not text or _has_any(text, "help", "what can you", "examples", "hi", "hello"):
        return HELP
    if m.purchases(df).empty and df.empty:
        return "There are no transactions in the current selection."

    months = find_months(text)
    if _has_any(text, "duplicate", "duplicates", "double charged", "charged twice"):
        return answer_duplicates(df)
    if _has_any(text, "fee", "fees"):
        return answer_fees(df)
    if _has_any(text, "refund", "refunds", "refunded"):
        return answer_refunds(df)
    if _has_any(text, "payment", "payments", "paid off", "pay off", "bill payment"):
        return answer_payments(df)
    if _has_any(text, "recurring", "commitment", "commitments", "fixed costs"):
        return answer_recurring(df)
    if _has_any(text, "weekend", "weekends", "weekday", "weekdays"):
        return answer_weekend(df)

    if len(months) >= 2 and _has_any(text, "compare", "vs", "versus", "against", "difference"):
        rows, label = _scope(text, df, use_months=False)
        return answer_compare(rows, label, months, df)

    rows, label = _scope(text, df)
    if _has_word(text, "month") and _has_any(text, "highest", "most", "biggest", "which", "peak", "worst"):
        rows, label = _scope(text, df, use_months=False)
        return answer_months(rows, label)
    by_category = _has_any(text, "category", "categories")
    ranks_things = by_category or _has_any(text, "merchant", "merchants", "shops", "places", "stores")
    if _has_any(text, "top", "favourite", "favorite", "where do i spend") or (
        ranks_things and _has_any(text, "most", "biggest", "largest")
    ):
        return answer_top(rows, label, "category" if by_category else "merchant", _top_n(text))
    if _has_any(text, "biggest", "largest", "most expensive", "highest", "expensive"):
        return answer_biggest(rows, label, _top_n(text))
    if _has_any(text, "how many", "how often", "number of", "times", "count"):
        return answer_count(rows, label, df)
    if _has_any(text, "average", "avg", "typical", "mean"):
        return answer_average(rows, label, df)
    if label or _has_any(text, "spend", "spent", "total", "cost", "how much"):
        return answer_total(rows, label, df)
    return "Sorry, I didn't understand that one. " + HELP
