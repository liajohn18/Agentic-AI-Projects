# Public demo deployment

This project is prepared as an educational Streamlit demo. The welcome screen is the entry view; reviewers can open the operations dashboard and upload the synthetic CSV/PDF examples.

## Streamlit Community Cloud

1. Create a GitHub repository for this project and push the project files.
2. Open [Streamlit Community Cloud](https://share.streamlit.io/) and choose **Create app**.
3. Select the repository, branch, and entry point `src/aml_agent/dashboard.py`.
4. Deploy, then use the generated `streamlit.app` URL to share the demo.

`requirements.txt` lists the Python dependencies for the hosted app.

## Hosted-demo limitations

- CSV batch analysis works with built-in illustrative rules and risk scoring without model calls. The optional **Run policy agent for this case** action in investigation details requires a reachable model service and runs one local-policy search for the selected case only.
- PDF transaction extraction and AI policy interpretation currently use Ollama. The Ollama server on a developer's computer is not reachable by a hosted app. Configure a private, reachable Ollama service before enabling these features publicly.
- Cases are stored in `data/aml_cases.db` using SQLite. On a demo host, this local file may not persist across restarts or redeploys. Use a managed database before relying on saved case history.
- Use synthetic data only. Do not upload real customer, account, identity, or KYC information to this public educational demo.

## Before sharing

- Confirm the repository contains no secrets, local database with personal data, or private uploads.
- Check the deployed app's logs after the first launch.
- Upload the supplied synthetic customer and transaction CSVs and verify a small batch before sharing the URL.
