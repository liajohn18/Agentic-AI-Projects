# Week 3 Project Documentation

## AML Investigation Agent

**Build track:** Code-heavy, using Python, LangChain, and LangGraph<br>
**Project type:** Bring-your-own use case<br>
**Interface:** Local Streamlit dashboard and a command-line batch runner
**Status:** Educational proof of concept using fictional data

## 1. Project overview

The AML Investigation Agent helps a reviewer examine a transaction together with its customer/KYC profile. It validates the data, applies transparent demo rules, calculates an illustrative risk score, searches a local demo policy, and prepares an evidence-linked case report. Transactions that meet the demo review criteria are paused for a human case disposition: close the alert with no further action, or escalate it for further review. Both options require a reviewer rationale.

The project is intended to demonstrate an investigation workflow, not to determine whether real activity is criminal or to satisfy a financial institution's compliance obligations.

### Agent goal in one sentence

> This agent helps a financial-crime reviewer triage fictional customer transactions in a local dashboard, replacing the manual steps of joining transaction and customer records and gathering initial review reasons; it validates data, runs rule and risk checks, searches demo policy text, and saves a case, while handing flagged transactions to a human reviewer, and it succeeds when each valid input is saved with the correct clear-or-review route and invalid rows are reported without stopping the rest of the CSV batch.

### User and task

- **Intended user:** A student or analyst exploring a financial-crime investigation workflow with synthetic records.
- **Multi-step task:** Import or extract a transaction; link it to a customer; validate it; check transaction and customer information; calculate a demo risk score; retrieve relevant demo policy; create a case when appropriate; collect a human decision; save and display the result.
- **Current success measure:** End-to-end completion rate for valid submitted records, with invalid rows counted separately. The `evaluate_demo.py` script also reports agreement with the separate synthetic labels. No measured performance result is claimed in this document; run the script to produce one.

## 2. Project framework

| Framework question | Current project answer |
|---|---|
| Where is it used? | Local Streamlit dashboard; a separate command-line runner is available for the included demo CSVs. |
| What steps does it take? | Validate; run compliance, risk, transaction, customer, and policy retrieval components; combine findings; analyze retrieved policy when relevant; create alert/case; route to human review or report; save to SQLite. |
| What can it do? | Validate structured records; extract one transaction from selectable-text PDF; apply deterministic rules; calculate a risk score; search local policy; pause/resume for human review; save review and case records; generate a Markdown report. |
| What does it remember? | LangGraph state during a run and an in-memory checkpoint for an interrupt; completed reviews in SQLite; the dashboard keeps some current-session state in Streamlit session state. |
| What should it never do? | It must not treat a score or flag as proof of wrongdoing, make a legal determination, or file a regulatory report. The demo policy and rules are not legal requirements. |
| Where is human review? | A transaction with review reasons pauses before its final workflow report. The reviewer records “close alert — no further action” or “escalate for further review,” with a required rationale. Clear transactions do not pause. |
| What happens when something breaks? | The dashboard records row-level CSV exceptions and continues with later rows. PDF extraction errors are shown in the interface. There is no general retry policy; the CLI runner can stop on an unhandled row or model error. |
| How is success measured? | Count valid records that reach a saved result and the expected route; separately count input errors, pending human reviews, and completed decisions. Synthetic-label metrics are reported separately by `evaluate_demo.py`. |

## 3. Architecture and workflow

The project uses a **coordinated specialist graph**. LangGraph owns the control flow and shared state. After validation, independent specialist nodes run in parallel and their results are combined. An optional, bounded policy investigation agent then decides whether to refine the local policy search, observes the search results, and repeats or stops. This is the project's ReAct-style loop; it is limited to read-only policy search.

```text
Input (CSV row or extracted PDF/text)
                 |
                 v
      Validate transaction + customer
                 |
        +--------+---------+---------+---------+
        |                  |         |         |
        v                  v         v         v
 Compliance check   Risk scoring   Transaction   Customer   Policy
   (Python)          (Python)      specialist   specialist retrieval
        |                  |         |         |         |
        +------------------+---------+---------+---------+
                                   |
                                   v
                         Synthesize findings
                                   |
                                   v
                  Policy agent: decide search or finish
                         |                 ^
               search policy              | observe results
                         +-----------------+
                                   |
                                   v
                      Citation-checked policy analysis
                                   |
                                   v
                         Create alert and case
                            /           \
                 Review required       Clear
                       |                 |
                       v                 v
                Human interrupt     Generate report
                       |                 ^
                       +-----------------+
                                   |
                                   v
                           Save to SQLite
                                   |
                                   v
                         Streamlit dashboard
```

### Workflow components

1. **Input and extraction:** CSV rows are parsed directly. The dashboard can extract a single transaction from a PDF with selectable text using `pypdf` and Ollama structured output. Scanned-image OCR is not configured.
2. **Validation:** `validate_transaction` validates transaction and customer objects against Pydantic schemas and records the source file and excerpt as evidence.
3. **Compliance check:** Python rules flag an amount over USD 10,000 or sender and beneficiary names that match.
4. **Specialist analysis:**
   - `transaction_specialist` applies deterministic transaction checks, including high-value amounts and high-value cash transactions.
   - `customer_specialist` checks the KYC risk rating, KYC status, expected turnover, and potential PEP/sanctions screening matches supplied in the customer record.
   - `policy_specialist` retrieves relevant sections from the local policy file using BM25 lexical search.
   - `assess_transaction_risk` calls the deterministic risk tool.
5. **Synthesis and policy analysis:** `synthesize_findings` combines compliance and specialist findings and determines whether review is needed. Batch upload skips model calls so large files can be processed quickly. For a flagged case, a reviewer can choose **Run policy agent for this case** in the investigation details. That bounded ReAct loop asks the configured Ollama model whether a focused local BM25 policy search would help, observes the retrieved passages, then makes a final decision. It is capped at one search and records an audit trace. This on-demand action does not generate a separate AI policy write-up; it saves the retrieved passages for the reviewer. If the model is unavailable, the issue is recorded and the rest of the case remains reviewable.
6. **Case routing:** If review is needed, `create_alert_and_case` creates an alert and case. `review_case` uses LangGraph `interrupt()` to pause for a human decision. If there are no review reasons, the graph proceeds to reporting without human review.
7. **Report and storage:** `generate_report` creates a Markdown report. `save_case` saves all transaction reviews and any alert/case records to SQLite.

### Specialist vs. non-agent components

The transaction and customer specialists are ordinary Python rule functions. Policy retrieval is local BM25 lexical search. Risk scoring and compliance are also deterministic Python. The optional policy investigation agent uses a structured Ollama decision to run at most one read-only policy search and inspect the result; it does not choose the human outcome. Policy interpretation and PDF extraction also use the configured Ollama model with structured Pydantic outputs. LangGraph coordinates these nodes; it is the orchestrator, not another LLM agent.

## 4. Data models and evidence

`src/aml_agent/schemas.py` defines the records and validation constraints:

- **`AMLTransaction`:** transaction ID, positive amount, 3-character currency, timestamp, sender, beneficiary, allowed channel, and description.
- **`Customer`:** customer ID, legal name, country, risk rating, plus optional KYC, turnover, source-of-funds, PEP, and sanctions fields.
- **`RiskAssessment`:** score from 0 to 1, low/medium/high level, indicators, and rationale.
- **`EvidenceRecord`:** evidence ID, source filename/type, locator, excerpt, optional field name, and confidence.
- **`AMLAlert` and `AMLCase`:** alert and case identifiers, linked customers/transactions, status, disposition, reviewer rationale, reviewer name, and timestamps.
- **`PolicyRagAnalysis`:** summary, policy-linked findings, supporting quotes, and questions for the reviewer.

Each graph run stores a source evidence record. For CSV uploads, the excerpt is the serialized source row and the locator is the transaction ID. The dashboard presents parsed fields as a field/value list. Retrieved policy references include a policy ID, filename, excerpt, and retrieval information; model-written policy findings are retained only when their quote can be found in the retrieved excerpt.

## 5. Risk and decision logic

The rule threshold and risk score are educational examples, not operational thresholds.

- Compliance flags amounts greater than USD 10,000 and matching sender/beneficiary names.
- Risk scoring starts at 0.10 and adds points for high amounts, cash channel, high customer risk, transaction size relative to expected turnover, or potential PEP/sanctions matches. The score is capped at 1.00.
- A score of 0.40 or more is medium; 0.70 or more is high.
- Human review is requested only when the illustrative risk level is High (score >= 0.70). Low- and medium-risk transactions pass automatically; their compliance and specialist signals remain in the report for context.
- This routing rule is a simplified demo choice. Real AML programs commonly require separate escalation controls for sanctions screening, PEP matches, data quality, and other institution-specific scenarios; this project must not be used to pass or clear real transactions.
- A reviewer can close an alert with no further action, or escalate the case for further review. A rationale is required and recorded with the reviewer name. This is a workflow disposition; it does not establish a legal finding, block a payment, or file a regulatory report.
- Case event history records case opening, policy search completion/failure, and reviewer disposition in the local SQLite database. This application log is useful for the demo but is not tamper-proof or a regulated audit system.
- The case view shows related transactions from the current upload only. It does not have a complete customer or account history, so the displayed 30-day totals must not be treated as full behavioral monitoring.

## 6. Tools, models, and dependencies

- **LangGraph:** graph state, parallel workflow nodes, conditional routing, interrupt/resume, and in-memory checkpointing.
- **LangChain Ollama integration:** structured extraction/analysis using `gemma4:e4b` by default. The policy model can be changed with `AML_POLICY_MODEL`.
- **Pydantic:** validates transactions, customers, risk assessments, cases, alerts, and structured model results.
- **Local BM25 policy search:** ranks sections from `data/policies/demo_aml_policy.md`; it is lexical retrieval, not embedding-based retrieval.
- **SQLite:** persists review and investigation results in `data/aml_cases.db`.
- **Streamlit:** dark-theme alert workbench with search/risk/status filters, case management, customer activity, data import, metrics, portfolio analytics, and case detail.
- **pypdf:** extracts selectable text from a single transaction PDF. OCR is not included.

## 7. Data used

The demo dataset is fictional and stored under `data/demo/`:

- `customers.csv`: 200 fictional customer/KYC profiles.
- `transactions.csv`: 400 fictional transactions linked to customers by `customer_id`.
- `reference_labels.csv`: illustrative labels and scenarios for evaluation only. The investigation graph does not load this file.
- `data/policies/demo_aml_policy.md`: fictional policy text for local retrieval, not law or an institution's approved policy.
- `data/demo/sample_transaction_upload.pdf`: a synthetic, text-based single-transaction PDF for the dashboard upload path.

Single-record examples used by the command-line demonstrations are grouped in `data/samples/`: `sample_transaction.txt` is the unstructured extractor input, `sample_customer.json` is its matching KYC profile, and `sample_txn.json` is an already structured transaction example.

The labels called `suspicious` and `legitimate` are demonstration labels. They are not verified findings about real activity. No real customer data should be placed in this demo.

## 8. Human handoff, state, and recovery

### Human-in-the-loop

For a flagged transaction, LangGraph pauses at `interrupt()`. The dashboard or CLI supplies a disposition and rationale through `Command(resume=...)` using the same thread ID. The graph then closes the alert without further action or escalates the case, creates the report, and saves the result. Clear transactions do not enter this human review step. The optional policy research action is available beside the pending case and is advisory; it does not make the disposition.

### State and persistence

The graph is compiled with `InMemorySaver`, so paused graph checkpoints are held in process memory. Completed review/case data are written to SQLite, but the checkpoint needed to resume a pending graph is not durable across an application restart. The dashboard's pending-review queue also uses Streamlit session state. Durable checkpoint storage and a persistent reviewer queue are future improvements.

### Error behavior

- Customer CSV parsing errors are displayed in the dashboard.
- CSV transaction rows are validated one at a time. An exception for a row is reported in the import summary, and processing proceeds to the next row.
- A PDF with no selectable text produces an error message. Missing `pypdf` or model/extraction errors are surfaced in the dashboard.
- The per-case policy investigation agent is optional and limited to one search. A model decision error stops the loop and leaves already available policy passages for human review; there is no retry/backoff policy.
- The CLI batch runner validates records and asks for decisions in the terminal, but it does not wrap every row and model call in a retry/recovery strategy.
- Automatic retries, timeouts, durable recovery after restart, and structured operational logs have not been implemented.

## 9. Evaluation and success criteria

Run the batch workflow, then compare saved results with the separate reference-label file:

```powershell
uv run python src/aml_agent/evaluate_demo.py
```

The script calculates true alerts, correct clears, false alerts, missed reference cases, accuracy, precision, recall, specificity, and the number of labeled transactions not yet processed. It reads labels only after the workflow and never supplies them to the graph.

Interpret the numbers only as agreement with this synthetic dataset. The dataset is small and intentionally illustrative; these metrics are not evidence of real-world AML effectiveness, regulatory compliance, or production readiness. No numerical score is reported here because the evaluation script has not been run as part of preparing this document.

For end-to-end workflow measurement, record at least:

1. Number of valid records submitted.
2. Number saved with a clear or review-required outcome.
3. Number of flagged cases resumed and closed by a human.
4. Number of invalid rows and errors.
5. Time from upload to completed review, if timed during the demo.

## 10. Running the project

Start Ollama and make sure the configured model is available. From the project root:

```powershell
uv sync
uv run streamlit run src/aml_agent/dashboard.py
```

For command-line batch processing of the included CSVs:

```powershell
uv run python src/aml_agent/try_batch.py
```

The CLI batch defaults to five rows. To process all transactions in `transactions.csv`:

```powershell
$env:AML_BATCH_LIMIT = "0"
uv run python src/aml_agent/try_batch.py
```

The dashboard defaults to analyzing five selected rows per CSV batch; setting the dashboard limit to zero selects all rows. The PDF path handles one transaction at a time and requires selectable text and a customer profile selected from the uploaded customer CSV. The uploaded demo transaction file includes synthetic `account_id` and `direction` fields; the activity panel aggregates matching rows in that upload only.

## 11. Prompting and build iterations

### Representative AI coding prompts

The following are paraphrases of the development requests from the project-building conversation, not an exact prompt log:

- Add a structured transaction extractor that returns the transaction schema from sample text.
- Expand the single-transaction workflow to process transaction CSV rows joined to customer/KYC profiles.
- Add transaction, customer, risk, and policy specialist components to the LangGraph pipeline.
- Add local policy retrieval and require policy analysis to cite a verifiable excerpt.
- Build a professional Streamlit dashboard for multiple cases and uploaded customer/transaction data.
- Make dashboard KPIs and workspace views update to reflect the latest analyzed batch.
- Make case details easier to understand by foregrounding the outcome, reason, evidence, policy references, and review decision.

### Runtime model instructions

- **Text extractor (`try_extractor.py`):** asks Ollama to extract only fields supported by the source, return the requested Pydantic schema, and normalize a date-only value to midnight UTC while stating that this is an assumption.
- **PDF extractor (`dashboard.py`):** asks for one transaction supported by the PDF text, forbids inferring missing values, and specifies how to handle a date without a time.
- **Policy investigation agent (`specialists.py`):** decides whether a refined local policy search is useful, with a three-search limit; treats customer, transaction, and retrieved policy text as untrusted data rather than instructions.
- **Policy analyst (`specialists.py`):** must use only retrieved fictional policy text; must not decide if activity is suspicious or approve/reject it; must use a supplied policy ID and an exact supporting quote; and must leave unsupported findings out. Transaction/customer data are treated as data, not instructions.
- Compliance and risk rules do not use prompts; their logic is Python code.

### Iterations and learnings

The implementation grew from schema validation and a single sample transaction into structured text extraction, a LangGraph workflow with human interrupts, customer-linked batch processing, SQLite persistence, specialist components and policy retrieval, a bounded policy-search loop, and a multi-page Streamlit dashboard. The dashboard now uses an alert-first workbench with separate Cases, Customers, and Data import destinations, and presents the coordinated specialist findings in each case detail.

Key learning: an end-to-end agentic workflow depends on more than a model response. It needs validated state, explicit routing, tool boundaries, human handoff, recoverable errors, evidence provenance, and a way to measure outcomes. In this prototype, some of those controls are implemented, while durable checkpoints, stronger retries, and validated performance on representative real-world data remain future work.

## 12. Limitations and next steps

This is a proof of concept, not a production AML system. It has fictional data and policy, fixed illustrative rules, a simple per-transaction score, lexical retrieval, and a bounded policy-only ReAct loop. The agent cannot choose tools outside local policy search. It does not provide jurisdiction-specific legal determinations, sanctions-list screening, beneficial-ownership verification, historical customer behavior analysis, network analysis, SAR filing, role-based access control, encryption/retention controls, or durable graph checkpoints. The human reviewer makes the demo decision; the system does not file reports or take external financial actions.

Reasonable next steps are:

1. Add a durable LangGraph checkpointer and persistent pending-review records.
2. Replace the demo SQLite event history with access-controlled, tamper-evident audit storage that records assignments, decisions, timestamps, and rule/policy versions.
3. Connect a complete, authorized customer/account history and add tested behavioral monitoring and alert grouping; the current activity panel only summarizes transactions in the current upload.
4. Link each finding to its exact source fields and calculation inputs.
5. Expand evaluation scenarios and review false positives and missed synthetic cases before changing rules.
6. Add authentication, role controls, data protection, and jurisdiction-specific policy only if the project is later developed beyond synthetic demonstration data.

## 13. Project files

| File | Purpose |
|---|---|
| `src/aml_agent/dashboard.py` | Streamlit imports, review queue, dashboard views, and PDF extraction UI. |
| `src/aml_agent/graph.py` | LangGraph state, workflow nodes, routing, human interrupt, and report generation. |
| `src/aml_agent/specialists.py` | Transaction/customer specialists, bounded policy investigation agent, and policy analysis specialist. |
| `src/aml_agent/risk_tools.py` | Deterministic illustrative risk calculation. |
| `src/aml_agent/policy.py` | BM25 search over local policy Markdown files. |
| `src/aml_agent/schemas.py` | Pydantic input, evidence, alert, case, risk, and policy schemas. |
| `src/aml_agent/storage.py` | SQLite persistence for review and investigation records. |
| `src/aml_agent/try_batch.py` | Command-line processor for demo CSV data. |
| `src/aml_agent/try_extractor.py` | Standalone text extraction example using Ollama. |
| `src/aml_agent/try_schema.py` | Standalone schema validation example. |
| `src/aml_agent/evaluate_demo.py` | Post-run comparison with separate synthetic reference labels. |
| `data/demo/` | Fictional customer, transaction, and evaluation data. |
| `data/policies/demo_aml_policy.md` | Fictional local policy corpus. |

## 14. Submission checklist

- [x] Project overview, use case, architecture, data, prompts/iterations, and learnings documented.
- [ ] Run the evaluation script and include its actual synthetic results with limitations.
- [ ] Record a demo video of five minutes or less.
- [ ] Upload the code to GitHub and include the repository link in the submission.
- [ ] Keep all data shown in the video fictional and avoid exposing secrets or personal data.
