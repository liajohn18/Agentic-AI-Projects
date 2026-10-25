"""Compare completed demo reviews with the separate synthetic label file."""

import csv
import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "aml_cases.db"
LABELS_PATH = PROJECT_ROOT / "data" / "demo" / "reference_labels.csv"


def main() -> None:
    with LABELS_PATH.open(encoding="utf-8", newline="") as file:
        labels = {
            row["transaction_id"]: row["reference_label"] == "suspicious"
            for row in csv.DictReader(file)
        }

    if not DB_PATH.exists():
        raise SystemExit("No results database found. Run try_batch.py first.")

    with sqlite3.connect(DB_PATH) as connection:
        try:
            rows = connection.execute(
                """
                SELECT transaction_id, compliance_flags, workflow_outcome
                FROM transaction_reviews
                """
            ).fetchall()
        except sqlite3.OperationalError as error:
            raise SystemExit(
                "No transaction_reviews table found. Run try_batch.py first."
            ) from error

    alert_outcomes = {
        "pending_human_review",
        "closed_no_action",
        "escalated_for_review",
        "human_approved",
        "human_rejected",
    }
    evaluated = [
        (transaction_id, labels[transaction_id], outcome in alert_outcomes)
        for transaction_id, _flags, outcome in rows
        if transaction_id in labels
    ]
    if not evaluated:
        raise SystemExit("No saved transactions match the reference labels yet.")

    tp = sum(actual and predicted for _, actual, predicted in evaluated)
    tn = sum(not actual and not predicted for _, actual, predicted in evaluated)
    fp = sum(not actual and predicted for _, actual, predicted in evaluated)
    fn = sum(actual and not predicted for _, actual, predicted in evaluated)
    total = len(evaluated)
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    not_processed = len(labels) - total

    print("Synthetic demo evaluation (not a measure of real AML effectiveness)")
    print(f"Evaluated saved transactions: {total}")
    print(f"Not yet processed: {not_processed}")
    print(f"True alerts: {tp} | Correct clears: {tn}")
    print(f"False alerts: {fp} | Missed reference cases: {fn}")
    print(f"Accuracy:    {accuracy:.1%}")
    print(f"Precision:   {precision:.1%}")
    print(f"Recall:      {recall:.1%}")
    print(f"Specificity: {specificity:.1%}")
    print(
        "Reference labels were read only by this evaluation script; "
        "they are not input to the investigation workflow."
    )


if __name__ == "__main__":
    main()
