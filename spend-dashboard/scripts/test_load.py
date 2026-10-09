"""Quick check of src/load.py. Run with: uv run python scripts/test_load.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.load import filter_data, load_data  # noqa: E402

FLAGS = ["is_weekend", "is_foreign", "is_recurring", "is_duplicate_suspect", "is_large"]


def main() -> None:
    """Print row count, category totals, flag counts and a filter example."""
    df = load_data()
    print(f"Rows: {len(df)}\n")

    totals = df.groupby("category")["amount_aed"].agg(["count", "sum"]).round(2)
    print("Category totals (AED):")
    print(totals.sort_values("sum", ascending=False).to_string(), "\n")

    print("Flag counts:")
    for flag in FLAGS:
        print(f"  {flag:22} {int(df[flag].sum())}")

    print("\nRecurring merchants:", sorted(df.loc[df["is_recurring"], "merchant"].unique()))
    print("\nDuplicate suspects:")
    dup_cols = ["txn_id", "txn_date", "merchant", "amount_aed"]
    print(df.loc[df["is_duplicate_suspect"], dup_cols].to_string(index=False))
    print("\nLarge purchases: min", df.loc[df["is_large"], "amount_aed"].min())

    subset = filter_data(df, "2026-08-01", "2026-08-31", exclude_travel=True, exclude_large=True)
    print(f"\nfilter_data(Aug 2026, exclude travel + large): {len(subset)} rows")


if __name__ == "__main__":
    main()
