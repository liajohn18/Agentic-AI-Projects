"""Validate the demo customer and transaction CSV files and join them by customer ID."""

import csv
import json
import os
from pathlib import Path

from graph import graph
from langgraph.types import Command
from schemas import AMLTransaction, Customer
from storage import save_case


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    data_folder = project_root / "data" / "demo"

    customers: dict[str, Customer] = {}
    with (data_folder / "customers.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        for row in csv.DictReader(file):
            customer = Customer.model_validate(row)
            customers[customer.customer_id] = customer

    processed_count = 0
    batch_limit = int(os.environ.get("AML_BATCH_LIMIT", "5"))
    if batch_limit < 0:
        raise ValueError("AML_BATCH_LIMIT must be 0 or a positive number")

    with (data_folder / "transactions.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        for row in csv.DictReader(file):
            customer_id = row.pop("customer_id")
            customer = customers.get(customer_id)
            if customer is None:
                raise ValueError(
                    f"Transaction references unknown customer: {customer_id}"
                )

            transaction = AMLTransaction.model_validate(row)
            config = {
                "configurable": {"thread_id": transaction.transaction_id}
            }
            result = graph.invoke(
                {
                    "raw_transaction": transaction.model_dump(mode="json"),
                    "raw_customer": customer.model_dump(mode="json"),
                    "source_file": "transactions.csv",
                    "source_text": json.dumps(row, ensure_ascii=False),
                },
                config=config,
            )

            if result.get("__interrupt__"):
                while True:
                    decision_value = input(
                        f"{transaction.transaction_id} needs review. "
                        "Enter 'close_no_action' or 'escalate': "
                    ).strip().casefold()
                    if decision_value in {"close_no_action", "escalate"}:
                        break
                    print("Please enter 'close_no_action' or 'escalate'.")

                rationale = input(
                    "Reviewer rationale (at least 10 characters): "
                ).strip()
                while len(rationale) < 10:
                    rationale = input("Please enter a brief rationale: ").strip()

                result = graph.invoke(
                    Command(
                        resume={
                            "decision": decision_value,
                            "rationale": rationale,
                            "reviewer": "demo_reviewer",
                        }
                    ),
                    config=config,
                )

            save_case(result)
            processed_count += 1
            print(
                f"Processed {transaction.transaction_id} for "
                f"{customer.legal_name}: {result['workflow_outcome']}"
            )

            # Default to five rows; set AML_BATCH_LIMIT=0 to process the full CSV.
            if batch_limit and processed_count >= batch_limit:
                break

    print(
        f"Finished: processed {processed_count} transactions from "
        f"{len(customers)} loaded customers."
    )
    print("Completed transaction reviews were saved to data/aml_cases.db.")
    if batch_limit:
        print("Set AML_BATCH_LIMIT=0 to process the entire transactions.csv file.")


if __name__ == "__main__":
    main()
