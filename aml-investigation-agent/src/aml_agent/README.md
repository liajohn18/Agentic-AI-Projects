# Application code guide

Open the file for the task you are working on:

| If you want to change… | Start here | Role |
|---|---|---|
| The screen, upload flow, dashboard, or review buttons | `dashboard.py` | Streamlit user interface |
| The order of processing, routing, or human approval pause | `graph.py` | LangGraph workflow |
| Transaction/customer specialist checks or policy agent behavior | `specialists.py` | Specialist and bounded policy-search logic |
| Input/output record shapes and validation | `schemas.py` | Pydantic data models |
| Risk score rules | `risk_tools.py` | Deterministic illustrative scoring |
| Local policy search | `policy.py` | BM25 retrieval over `data/policies/` |
| Saving and reading investigation cases | `storage.py` | SQLite access |
| Command-line processing of the synthetic CSV batch | `try_batch.py` | Batch demonstration |
| Extracting a transaction from sample text | `try_extractor.py` | Ollama extraction demonstration |
| Validating a sample structured transaction | `try_schema.py` | Schema demonstration |
| Comparing saved cases to synthetic labels | `evaluate_demo.py` | Evaluation utility |

The `try_*.py` files are small runnable demonstrations. The main dashboard is `dashboard.py`; the main workflow is `graph.py`.
