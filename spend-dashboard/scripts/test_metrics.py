"""Quick check of src/metrics.py. Run with: uv run python scripts/test_metrics.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import metrics as m  # noqa: E402
from src.load import load_data  # noqa: E402


def main() -> None:
    """Print every KPI on the full data, raw and formatted."""
    df = load_data()
    category, share = m.top_category(df)
    rows = [
        ("total_net_spend", m.total_net_spend(df), m.fmt_aed(m.total_net_spend(df))),
        ("avg_monthly_spend", m.avg_monthly_spend(df), m.fmt_aed(m.avg_monthly_spend(df))),
        ("mom_change", m.mom_change(df), f"{m.mom_change(df):+.1%}"),
        ("txn_count", m.txn_count(df), f"{m.txn_count(df):,}"),
        ("avg_txn_value", m.avg_txn_value(df), m.fmt_aed(m.avg_txn_value(df), 2)),
        ("top_category", (category, share), f"{category} ({share:.1%})"),
        ("monthly_commitments", m.monthly_commitments(df), m.fmt_aed(m.monthly_commitments(df))),
        ("delivery_share", m.delivery_share(df), f"{m.delivery_share(df):.1%}"),
        ("total_fees", m.total_fees(df), m.fmt_aed(m.total_fees(df), 2)),
        ("payment_coverage", m.payment_coverage(df), f"{m.payment_coverage(df):.1%}"),
    ]
    for name, raw, formatted in rows:
        print(f"{name:20} {formatted:24} raw={raw}")

    print("\nMonthly net spend:")
    print(m.monthly_net_spend(df).round(2).to_string())


if __name__ == "__main__":
    main()
