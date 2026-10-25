Synthetic AML investigation demo dataset
=========================================

All names and records in this folder are fictional and generated for software testing.
customers.csv: 200 fictional company KYC profiles.
transactions.csv: 400 fictional transactions (two per customer). customer_id links each transaction to customers.csv. account_id and direction are synthetic fields used by the dashboard's related-activity view.
reference_labels.csv: synthetic example labels for evaluation only. Do not load this file into the investigation or screening workflow.

The label 'suspicious' is an illustrative reference label, not a real AML finding or proof of illegality.
The examples include routine transactions, amounts above the project's example review limit, same-sender/beneficiary cases, and high-amount cash cases.

Project workflow notes
----------------------

The graph has separate deterministic specialist nodes for transaction review,
customer due diligence, policy retrieval, and risk scoring. The local policy
file under data/policies is fictional training material, not regulatory advice.
Reference labels are read only by src/aml_agent/evaluate_demo.py after a batch
has been processed; the investigation graph must not use those labels.

Run the local dashboard from the project root with:
  uv run streamlit run src/aml_agent/dashboard.py

The dashboard supports linked customer and transaction CSV uploads. Only
High-risk transactions (illustrative score >= 0.70) enter human review;
lower-risk findings remain available as context. A single-transaction PDF
needs selectable text and a matching uploaded customer profile. Scanned-image
OCR is not configured. The project already declares pypdf as a dependency;
install project dependencies from the project root with:
  uv sync

Evaluate the processed transactions against the synthetic labels with:
  uv run python src/aml_agent/evaluate_demo.py

Evaluation results describe agreement with synthetic demo labels only and do
not measure real-world AML effectiveness.

Human review records one of two demo dispositions: close the alert with no
further action, or escalate the case for further review. A reviewer name and
rationale are required. These actions update the demo case workflow; they do
not approve/block a payment, determine criminality, or file a regulatory report.
The case event history is stored in the local SQLite database and is not a
tamper-proof audit system. Related activity summarizes only the transactions
in the current upload, not a complete customer/account history.
