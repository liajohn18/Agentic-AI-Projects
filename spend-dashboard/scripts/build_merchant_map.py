"""Build data/merchant_map.csv from the unique descriptions in data/transactions.csv.

Run with: uv run python scripts/build_merchant_map.py
"""

import re
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"

CATEGORIES = {
    "Food Delivery", "Groceries", "Dining & Coffee", "Online Shopping",
    "Retail & Fashion", "Utilities & Telecom", "Subscriptions", "Health & Fitness",
    "Transport", "Entertainment", "Travel", "Fees", "Payments", "Refunds",
}

# (regex matched against the start of the description, merchant, category, unsure)
# Order matters: the first match wins, so special rows come before merchant rules.
RULES = [
    (r"PAYMENT RECEIVED", "Card Payment", "Payments", False),
    (r"ANNUAL CARD FEE", "Annual Card Fee", "Fees", False),
    (r"FOREIGN TRANSACTION FEE", "Foreign Transaction Fee", "Fees", False),
    (r"AMAZON\.AE REFUND", "Amazon", "Refunds", False),
    (r"ZARA DUBAI MALL REFUND", "Zara", "Refunds", False),
    # London trip (GBP)
    (r"DISHOOM", "Dishoom", "Travel", False),
    (r"PREMIER INN", "Premier Inn", "Travel", False),
    (r"PRET A MANGER", "Pret A Manger", "Travel", False),
    (r"SELFRIDGES", "Selfridges", "Travel", False),
    (r"TFL TRAVEL", "TfL", "Travel", False),
    # Food delivery
    (r"TALABAT", "Talabat", "Food Delivery", False),
    (r"DELIVEROO", "Deliveroo", "Food Delivery", False),
    (r"KEETA", "Keeta", "Food Delivery", False),
    # Groceries
    (r"CARREFOUR", "Carrefour", "Groceries", False),
    (r"LULU HYPERMARKET", "Lulu Hypermarket", "Groceries", False),
    (r"SPINNEYS", "Spinneys", "Groceries", False),
    # Dining & coffee
    (r"%ARABICA", "%Arabica", "Dining & Coffee", False),
    (r"STARBUCKS", "Starbucks", "Dining & Coffee", False),
    (r"TIM HORTONS", "Tim Hortons", "Dining & Coffee", False),
    (r"SHAKE SHACK", "Shake Shack", "Dining & Coffee", False),
    (r"THE CHEESECAKE FACTORY", "The Cheesecake Factory", "Dining & Coffee", False),
    (r"ZUMA", "Zuma", "Dining & Coffee", False),
    # Shopping
    (r"AMAZON\.AE", "Amazon", "Online Shopping", False),
    (r"NOON\.COM", "Noon.com", "Online Shopping", False),
    (r"PAYPAL \*XJ7 TECHSVCS", "PayPal (XJ7 TechSvcs)", "Online Shopping", True),
    (r"ZARA", "Zara", "Retail & Fashion", False),
    (r"SHARAF DG", "Sharaf DG", "Retail & Fashion", True),
    (r"IKEA", "IKEA", "Retail & Fashion", True),
    # Utilities & telecom
    (r"DEWA", "DEWA", "Utilities & Telecom", False),
    (r"DU POSTPAID", "du", "Utilities & Telecom", False),
    # Subscriptions
    (r"NETFLIX", "Netflix", "Subscriptions", False),
    (r"SPOTIFY", "Spotify", "Subscriptions", False),
    (r"ANGHAMI", "Anghami", "Subscriptions", False),
    (r"SHAHID", "Shahid VIP", "Subscriptions", False),
    (r"APPLE\.COM/BILL", "Apple iCloud", "Subscriptions", False),
    # Health & fitness
    (r"FITNESS FIRST", "Fitness First", "Health & Fitness", True),
    (r"BOOTS PHARMACY", "Boots Pharmacy", "Health & Fitness", False),
    # Transport
    (r"UBER", "Uber", "Transport", False),
    (r"CAREEM", "Careem", "Transport", False),
    (r"SALIK", "Salik", "Transport", False),
    (r"ENOC", "ENOC", "Transport", False),
    (r"ADNOC", "ADNOC", "Transport", False),
    # Entertainment
    (r"VOX CINEMAS", "VOX Cinemas", "Entertainment", False),
]


def map_description(description: str) -> tuple[str, str, bool]:
    """Return (merchant, category, unsure) for a raw description."""
    for pattern, merchant, category, unsure in RULES:
        if re.match(pattern, description):
            return merchant, category, unsure
    raise ValueError(f"No rule matches description: {description!r}")


def main() -> None:
    """Write merchant_map.csv and print the rows that need review."""
    descriptions = sorted(pd.read_csv(DATA / "transactions.csv")["description"].unique())
    rows, unsure = [], []
    for desc in descriptions:
        merchant, category, flag = map_description(desc)
        assert category in CATEGORIES, category
        rows.append({"raw_description": desc, "merchant": merchant, "category": category})
        if flag:
            unsure.append((desc, merchant, category))

    pd.DataFrame(rows).to_csv(DATA / "merchant_map.csv", index=False)
    print(f"Wrote {len(rows)} rows to {DATA / 'merchant_map.csv'}")
    print("Needs review:")
    for desc, merchant, category in unsure:
        print(f"  {desc!r} -> {merchant} / {category}")


if __name__ == "__main__":
    main()
