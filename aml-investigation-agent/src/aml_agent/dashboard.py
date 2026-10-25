import ast
import csv
import html
import io
import json
import sqlite3
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
from langchain_ollama import ChatOllama
from langgraph.types import Command

from graph import generate_report, graph
from schemas import AMLTransaction, Customer
from storage import (
    load_case_events,
    load_policy_investigation,
    record_case_event,
    save_case,
    save_policy_investigation,
)
from specialists import policy_investigation_graph


DB_PATH = Path(__file__).resolve().parents[2] / "data" / "aml_cases.db"


@st.cache_resource
def _policy_agent_runtime() -> tuple[ThreadPoolExecutor, dict[str, Future], threading.Lock]:
    """Keep worker jobs alive across Streamlit script reruns and page changes."""
    return (
        ThreadPoolExecutor(max_workers=2, thread_name_prefix="aml-policy-agent"),
        {},
        threading.Lock(),
    )

st.set_page_config(
    page_title="Northstar | Financial Crime Operations",
    page_icon="N",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');

    :root {
        --ink: #f2f5f8;
        --muted: #aab8c7;
        --line: #405265;
        --surface: #26394a;
        --canvas: #1b2a38;
        --navy: #142230;
        --teal: #f04b96;
        --amber: #ff7b45;
        --red: #ff527a;
    }
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .stApp { background: var(--canvas); color: var(--ink); }
    [data-testid="stHeader"] { background: #1b2a38 !important; }
    [data-testid="stAppViewContainer"] .main .block-container { padding-top:3rem !important; }
    [data-testid="stSidebar"] .block-container { padding-top:.65rem !important; }
    [data-testid="stSidebar"] { background: #142230; border-right:1px solid #34485b; overflow-x:hidden; }
    [data-testid="stSidebar"] .block-container {
        width:100%; max-width:none; box-sizing:border-box;
        padding-left:1.35rem !important; padding-right:1rem !important;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"],
    [data-testid="stSidebar"] [role="radiogroup"] { width:100%; box-sizing:border-box; }
    [data-testid="stSidebar"] [role="radio"] { padding-left:.45rem; }
    [data-testid="stSidebar"] * { color: #e8f0f7; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { padding: 7px 0; }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #9fb2c7; }
    .block-container { padding-top: .65rem; padding-bottom: 3rem; max-width: 1500px; }
    h1, h2, h3 { font-family: 'Manrope', sans-serif !important; color: var(--ink); }
    h1 { font-size: 1.8rem !important; letter-spacing: -.04em; }
    h2 { font-size: 1.2rem !important; letter-spacing: -.025em; }
    h3 { font-size: 1rem !important; }
    .brand-mark { font-family: 'Manrope',sans-serif; font-weight: 800; font-size: 1.23rem; color: white; letter-spacing: -.04em; }
    .brand-sub { color: #93a9bf; font-size: .73rem; letter-spacing: .11em; text-transform: uppercase; margin-top: 3px; }
    .eyebrow { display:block; width:max-content; color:#ff91bd; background:transparent; border:0; border-radius:0; padding:0; font-size:.62rem; font-weight:800; text-transform:uppercase; letter-spacing:.14em; line-height:1.3; margin-bottom:.32rem; text-decoration:none; }
    .page-subtitle { color: var(--muted); margin:.22rem 0 0; font-size:.88rem; line-height:1.4; }
    .topline { display:flex; justify-content:space-between; align-items:center; gap:1rem; margin-bottom:.8rem; }
    .topline > div:first-child { flex:1 1 0; min-width:0; }
    .topline h1 { max-width:100%; font-size:1.55rem !important; line-height:1.14 !important; overflow-wrap:anywhere; word-break:normal; }
    @media (max-width: 700px) {
        .topline { flex-direction:column; align-items:flex-start; }
        .topline h1 { font-size:1.35rem !important; }
        .topline .live-pill { align-self:flex-start; }
    }
    [data-testid="stAppViewContainer"] { background:var(--canvas); }
    .live-pill { display:inline-flex; align-items:center; gap:.45rem; background:#213d49; color:#8de1d0; border:1px solid #37665e; border-radius:999px; padding:.42rem .72rem; font-size:.75rem; font-weight:700; }
    .live-dot { width:7px; height:7px; background:#35c6a2; border-radius:50%; display:inline-block; }
    .metric-card { background:var(--surface); border:1px solid var(--line); border-radius:7px; padding:16px 18px; min-height:108px; height:100%; box-sizing:border-box; display:flex; flex-direction:column; justify-content:space-between; box-shadow:0 5px 15px rgba(4,12,20,.14); }
    .metric-label { color:#c2ced9; font-size:.78rem; font-weight:700; letter-spacing:.035em; line-height:1.35; min-height:2.7em; }
    .metric-value { color:#ff7545; font-family:'Manrope',sans-serif; font-size:1.85rem; font-weight:800; letter-spacing:-.035em; margin-top:3px; line-height:1.1; min-height:1.1em; }
    .section-head { display:flex; justify-content:space-between; align-items:center; margin:1.45rem 0 .7rem; }
    .section-title { color:var(--ink); font-family:'Manrope',sans-serif; font-weight:700; font-size:1.04rem; }
    .panel { background:var(--surface); border:1px solid var(--line); border-radius:7px; padding:18px 20px; }
    .detail-label { color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; font-weight:700; margin-bottom:4px; }
    .detail-value { color:var(--ink); font-weight:600; font-size:.91rem; margin-bottom:14px; overflow-wrap:anywhere; }
    .risk-high { color:var(--red); font-weight:700; }
    .risk-medium { color:var(--amber); font-weight:700; }
    .risk-low { color:var(--teal); font-weight:700; }
    .data-table-wrap { width:100%; max-width:100%; overflow-x:auto; overflow-y:hidden; background:#243748; border:1px solid var(--line); border-radius:7px; scrollbar-color:#71869a #1d2d3c; scrollbar-width:thin; }
    table.data-table { width:100%; border-collapse:collapse; font-size:.82rem; min-width:850px; }
    table.customer-data-table { min-width:1080px; table-layout:auto; }
    .customer-data-table th:nth-child(1) { min-width:125px; }
    .customer-data-table th:nth-child(2) { min-width:210px; }
    .customer-data-table th:nth-child(3), .customer-data-table th:nth-child(4) { min-width:105px; }
    .customer-data-table th:nth-child(5), .customer-data-table th:nth-child(6), .customer-data-table th:nth-child(7) { min-width:105px; text-align:center; }
    .customer-data-table td:nth-child(5), .customer-data-table td:nth-child(6), .customer-data-table td:nth-child(7) { text-align:center; font-variant-numeric:tabular-nums; }
    .customer-table-hint { color:#aab8c7; font-size:.76rem; margin:.3rem 0 .55rem; }
    .data-table th { text-align:left; color:#aebdcb; font-size:.69rem; letter-spacing:.07em; text-transform:uppercase; background:#1d2d3c; padding:12px 13px; border-bottom:1px solid var(--line); white-space:nowrap; }
    .data-table td { color:#e1e8ee; padding:12px 13px; border-bottom:1px solid #35495b; white-space:nowrap; }
    .data-table tr:last-child td { border-bottom:0; }
    .data-table tr:hover td { background:#2b4052; }
    .data-table-wrap::-webkit-scrollbar { height:10px; }
    .data-table-wrap::-webkit-scrollbar-track { background:#1d2d3c; border-radius:99px; }
    .data-table-wrap::-webkit-scrollbar-thumb { background:#71869a; border:2px solid #1d2d3c; border-radius:99px; }
    .table-id { color:#ff8ab8; font-weight:700; }
    .badge { display:inline-block; padding:3px 8px; border-radius:999px; font-size:.7rem; font-weight:700; background:#34495b; color:#d7e0e8; }
    .badge-high { background:#522d3d; color:#ff8ea4; }
    .badge-medium { background:#51402e; color:#ffc17c; }
    .badge-low { background:#234b48; color:#77d9c7; }
    .chart-panel { background:#243748; border:1px solid var(--line); border-radius:7px; padding:14px 16px; min-height:244px; }
    .outcome-layout { display:flex; align-items:center; justify-content:center; gap:24px; min-height:210px; flex-wrap:wrap; }
    .outcome-donut { width:150px; height:150px; border-radius:50%; display:grid; place-items:center; flex:0 0 auto; }
    .outcome-donut-hole { width:88px; height:88px; border-radius:50%; background:#243748; display:grid; place-content:center; text-align:center; color:#f2f5f8; font-weight:800; font-size:1.15rem; }
    .outcome-donut-hole span { color:#aab8c7; font-size:.62rem; font-weight:600; text-transform:uppercase; letter-spacing:.07em; }
    .outcome-legend { min-width:160px; }
    .outcome-legend-row { display:flex; align-items:center; gap:8px; color:#d7e0e8; font-size:.8rem; margin:9px 0; }
    .outcome-dot { width:9px; height:9px; border-radius:50%; flex:0 0 auto; }
    .welcome-hero { position:relative; overflow:hidden; border:1px solid #5d4253; border-radius:22px; padding:clamp(28px,5vw,64px); background:radial-gradient(circle at 82% 20%,rgba(240,75,150,.22),transparent 28%),linear-gradient(125deg,#263849 0%,#172637 58%,#34283a 100%); box-shadow:0 24px 60px rgba(3,10,18,.24); }
    .welcome-hero:after { content:''; position:absolute; width:340px; height:340px; right:-100px; bottom:-190px; border:1px solid rgba(255,123,69,.45); border-radius:50%; box-shadow:0 0 0 32px rgba(255,123,69,.035),0 0 0 64px rgba(240,75,150,.04); pointer-events:none; }
    .welcome-kicker { color:#ff91bd; text-transform:uppercase; font-size:.72rem; font-weight:800; letter-spacing:.17em; }
    .welcome-title { max-width:850px; margin:18px 0 12px; color:#f7f8fa; font-family:'Manrope',sans-serif; font-size:clamp(2.2rem,5vw,4.2rem); font-weight:800; line-height:1.05; letter-spacing:-.055em; }
    .welcome-title span { color:#ff9b64; }
    .welcome-copy { max-width:700px; color:#c2ced9; font-size:1.02rem; line-height:1.65; }
    .welcome-status { display:inline-flex; gap:8px; align-items:center; margin-top:14px; padding:8px 12px; border:1px solid #405265; border-radius:999px; background:#1b2a38; color:#d7e0e8; font-size:.78rem; }
    .welcome-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:20px 0 30px; }
    .welcome-feature { height:100%; padding:20px; border:1px solid #405265; border-radius:12px; background:#243748; }
    .welcome-feature h3 { margin:0 0 8px; color:#f2f5f8; font-size:.98rem; }
    .welcome-feature p { margin:0; color:#aab8c7; font-size:.84rem; line-height:1.55; }
    .welcome-step { color:#ff9b64; font-size:.72rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; margin-bottom:9px; }
    @media (max-width: 760px) { .welcome-grid { grid-template-columns:1fr; } }
    [data-testid="stMetric"] { background:var(--surface); border:1px solid var(--line); border-radius:7px; padding:14px 16px; }
    [data-testid="stMetricLabel"] { color:var(--muted); white-space:normal !important; overflow:visible !important; text-overflow:clip !important; min-height:2.4em; align-items:flex-start; }
    [data-testid="stMetricLabel"] * { white-space:normal !important; overflow:visible !important; text-overflow:clip !important; overflow-wrap:anywhere; }
    [data-testid="stMetricValue"] { color:var(--ink); font-family:'Manrope',sans-serif; font-size:clamp(1.15rem,1.8vw,1.65rem) !important; line-height:1.15; letter-spacing:-.04em; white-space:nowrap; overflow:visible; }
    .insight-note { background:#253b4d; border-left:4px solid #f04b96; border-radius:6px; padding:12px 15px; color:#d7e0e8; margin:.6rem 0 1rem; }
    [data-testid="stVerticalBlockBorderWrapper"] { background:#243748; border-color:var(--line) !important; border-radius:7px; }
    [data-testid="stAlert"] { background:#26394a; color:var(--ink); }
    div[data-testid="stExpander"], div[data-testid="stExpander"] details,
    div[data-testid="stExpander"] summary,
    div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        background:#243748 !important; border-color:var(--line) !important; color:var(--ink) !important;
    }
    div[data-testid="stExpander"] summary p,
    div[data-testid="stExpander"] summary span { color:var(--ink) !important; }
    div[data-testid="stExpander"] summary:hover { background:#2b4052 !important; }
    div[data-baseweb="select"] > div, div[data-baseweb="input"] > div,
    input, textarea { background:#243748 !important; color:var(--ink) !important; border-color:var(--line) !important; }
    div[role="listbox"], div[role="option"] { background:#243748 !important; color:var(--ink) !important; }
    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploaderDropzone"] {
        background:#243748 !important; border:1px dashed #61778b !important; border-radius:8px !important;
    }
    [data-testid="stFileUploader"] section:hover,
    [data-testid="stFileUploaderDropzone"]:hover { border-color:#f04b96 !important; }
    [data-testid="stFileUploader"] button {
        background:#d72f82 !important; color:#ffffff !important; border:1px solid #f04b96 !important;
    }
    [data-testid="stFileUploader"] button:hover { background:#ed438f !important; }
    [data-testid="stFileUploader"] button *,
    [data-testid="stFileUploaderDropzoneInstructions"],
    [data-testid="stFileUploaderDropzoneInstructions"] * { color:#f2f5f8 !important; }
    [data-testid="stFileUploader"] small { color:#b8c5d1 !important; }
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
        background:#26394a !important; border:1px solid #405265 !important; color:#f2f5f8 !important;
    }
    [data-testid="stCheckbox"] input:checked + div { background:#d72f82 !important; border-color:#f04b96 !important; }
    [data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li { color:var(--ink); }
    .chart-row { display:grid; grid-template-columns:75px 1fr 32px; gap:10px; align-items:center; margin:17px 0; color:#bdc9d4; font-size:.8rem; }
    .chart-track { height:9px; background:#34495b; border-radius:99px; overflow:hidden; }
    .chart-fill { height:100%; border-radius:99px; }
    div[data-testid="stSelectbox"] label, div[data-testid="stTextInput"] label { color:var(--muted); font-weight:600; }
    .stButton button, .stDownloadButton button { border-radius:8px; font-weight:600; background:#d72f82 !important; color:#fff !important; border:1px solid #e84a96 !important; }
    .stButton button:hover, .stDownloadButton button:hover { background:#ed438f !important; border-color:#ff70ad !important; }
    hr { border-color:var(--line); }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=5)
def load_reviews() -> list[dict]:
    if not DB_PATH.exists():
        return []

    try:
        with sqlite3.connect(DB_PATH) as connection:
            connection.row_factory = sqlite3.Row
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            review_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(transaction_reviews)"
                )
            }
            evidence_column = (
                "r.evidence_data" if "evidence_data" in review_columns
                else "NULL AS evidence_data"
            )
            policy_column = (
                "r.policy_data" if "policy_data" in review_columns
                else "NULL AS policy_data"
            )
            case_join = (
                "LEFT JOIN investigations i ON i.transaction_id = r.transaction_id"
                if "investigations" in tables
                else ""
            )
            case_columns = (
                "i.case_id, i.alert_id, i.case_data, "
                if "investigations" in tables
                else "NULL AS case_id, NULL AS alert_id, NULL AS case_data, "
            )
            rows = connection.execute(
                f"""
                SELECT r.transaction_id, r.customer_id, r.transaction_data,
                       r.customer_data, r.risk_assessment, r.compliance_flags,
                       r.workflow_outcome, r.human_decision, r.report,
                       {evidence_column}, {policy_column}, {case_columns}
                       r.rowid AS saved_order
                FROM transaction_reviews r
                {case_join}
                ORDER BY r.rowid DESC
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return []

    reviews = []
    for row in rows:
        transaction = json.loads(row["transaction_data"])
        customer = json.loads(row["customer_data"])
        risk = json.loads(row["risk_assessment"])
        flags = json.loads(row["compliance_flags"])
        saved_policy = json.loads(row["policy_data"] or "[]")
        if isinstance(saved_policy, dict):
            policy_references = saved_policy.get("references", [])
            policy_analysis = saved_policy.get("analysis", {})
        else:
            policy_references = saved_policy
            policy_analysis = {}
        timestamp = datetime.fromisoformat(
            transaction["timestamp"].replace("Z", "+00:00")
        )
        case_data = json.loads(row["case_data"]) if row["case_data"] else {}
        amount = float(transaction["amount"])

        reviews.append(
            {
                "transaction_id": row["transaction_id"],
                "customer_id": row["customer_id"],
                "customer_name": customer["legal_name"],
                "country": customer["country_code"],
                "customer_risk": customer["risk_rating"].title(),
                "amount_value": amount,
                "amount_label": f'{transaction["currency"]} {amount:,.2f}',
                "currency": transaction["currency"],
                "account_id": transaction.get("account_id"),
                "direction": transaction.get("direction"),
                "timestamp": timestamp,
                "date_label": timestamp.strftime("%d %b %Y, %H:%M UTC"),
                "sender": transaction["sender_name"],
                "beneficiary": transaction["beneficiary_name"],
                "channel": transaction["channel"].title(),
                "description": transaction["description"],
                "risk": risk["risk_level"].title(),
                "risk_score": float(risk["risk_score"]),
                "indicators": risk.get("indicators", []),
                "rationale": risk.get("rationale", ""),
                "flags": flags,
                "flag_label": "; ".join(flags) if flags else "No rule flags",
                "outcome": row["workflow_outcome"],
                "decision": _decision_label(row["human_decision"], row["workflow_outcome"]),
                "decision_rationale": case_data.get("decision_rationale"),
                "reviewer": case_data.get("reviewer"),
                "case_id": row["case_id"],
                "alert_id": row["alert_id"],
                "case_status": case_data.get("status", "No case"),
                "report": row["report"],
                "evidence": json.loads(row["evidence_data"] or "[]"),
                "policy_references": policy_references,
                "policy_analysis": policy_analysis,
                "_transaction": transaction,
                "_customer": customer,
                "_risk_assessment": risk,
                "review_reasons": _report_list(row["report"], "Review reasons"),
            }
        )

    return reviews


def _decision_label(decision: str | None, outcome: str) -> str:
    labels = {
        "close_no_action": "Closed — no further action",
        "escalate": "Escalated for further review",
        "approve": "Legacy demo approval",
        "reject": "Legacy demo rejection",
    }
    if decision:
        return labels.get(decision, decision.replace("_", " ").title())
    return {
        "pending_human_review": "Awaiting reviewer",
        "auto_cleared_below_threshold": "Passed — below high-risk threshold",
        "no_rule_flags": "Not required",
    }.get(outcome, "Not recorded")


def metric_card(label: str, value: str) -> None:
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def _report_list(report: str, label: str) -> list[str]:
    prefix = f"- {label}: "
    for line in (report or "").splitlines():
        if line.startswith(prefix):
            try:
                value = ast.literal_eval(line[len(prefix):])
                return value if isinstance(value, list) else []
            except (ValueError, SyntaxError):
                return []
    return []


def _run_policy_agent_job(row: dict) -> dict:
    """Run and persist the selected-case research outside Streamlit's render thread."""
    try:
        state = policy_investigation_graph.invoke(
            {
                "transaction": row["_transaction"],
                "customer": row["_customer"],
                "review_reasons": row["review_reasons"] or row["flags"],
                "risk_assessment": row["_risk_assessment"],
                "requires_review": True,
                "policy_references": row["policy_references"],
                "run_policy_agent": True,
                "policy_search_iterations": 0,
                "policy_agent_log": [],
            }
        )
        search_trace = state.get("policy_agent_log", [])
        searched = any(item.get("status") == "searched" for item in search_trace)
        analysis = {
            "mode": "search_only",
            "summary": (
                "The policy investigation agent searched the local demo policy. "
                if searched
                else "The policy investigation agent did not complete a policy search. "
            ) + "Review any available passages; the agent does not make the case decision.",
            "findings": [],
            "open_questions": [],
            "model": None,
            "search_trace": search_trace,
            "search_status": state.get("policy_agent_status", "finished"),
        }
        references = state.get("policy_references", row["policy_references"])
        save_policy_investigation(row["transaction_id"], references, analysis)
        agent_failed = analysis["search_status"] == "agent_error"
        record_case_event(
            row["transaction_id"], row.get("case_id"),
            "policy_search_failed" if agent_failed else "policy_search_completed",
            "policy_research_agent",
            {
                "status": analysis["search_status"],
                "searches": search_trace,
                "policy_ids": [item.get("policy_id") for item in references],
            },
        )
        return {
            "ok": not agent_failed,
            "error": "The Ollama model could not make a policy-search decision." if agent_failed else None,
        }
    except Exception as error:
        trace = [{"status": "agent_error", "message": str(error)[:300]}]
        analysis = {
            "mode": "search_only",
            "summary": "The optional policy search did not complete. The reviewer can continue with the case using the available information.",
            "findings": [],
            "open_questions": [],
            "model": None,
            "search_trace": trace,
            "search_status": "agent_error",
        }
        try:
            save_policy_investigation(
                row["transaction_id"], row["policy_references"], analysis
            )
            record_case_event(
                row["transaction_id"], row.get("case_id"),
                "policy_search_failed", "policy_research_agent",
                {"error": str(error)[:300]},
            )
        except Exception:
            pass
        return {"ok": False, "error": str(error)[:300]}


def submit_policy_agent_for_case(row: dict) -> bool:
    """Queue one policy-search job per case without blocking page navigation."""
    transaction_id = row["transaction_id"]
    executor, jobs, lock = _policy_agent_runtime()
    with lock:
        existing = jobs.get(transaction_id)
        if existing is not None and not existing.done():
            return False
        jobs[transaction_id] = executor.submit(
            _run_policy_agent_job, dict(row)
        )
    return True


def policy_agent_job_status(transaction_id: str) -> dict | None:
    """Read and consume the finished job status from the Streamlit thread."""
    _, jobs, lock = _policy_agent_runtime()
    with lock:
        future = jobs.get(transaction_id)
        if future is None or not future.done():
            return {"status": "running"} if future is not None else None
        try:
            result = future.result()
        except Exception as error:
            result = {"ok": False, "error": str(error)[:300]}
        del jobs[transaction_id]
    return {"status": "finished", **result}


def policy_agent_job_running(transaction_id: str) -> bool:
    """Check background-job activity without consuming its eventual result."""
    _, jobs, lock = _policy_agent_runtime()
    with lock:
        future = jobs.get(transaction_id)
        return future is not None and not future.done()


def active_policy_agent_jobs() -> list[str]:
    """Return case IDs with background policy searches still in progress."""
    _, jobs, lock = _policy_agent_runtime()
    with lock:
        return [
            transaction_id
            for transaction_id, future in jobs.items()
            if not future.done()
        ]


def render_welcome_page(last_import: dict | None, analyzed_count: int) -> None:
    upload_text = (
        f'{analyzed_count:,} transaction(s) in your latest upload'
        if last_import is not None
        else "Ready for your first transaction upload"
    )
    st.markdown(
        '<section class="welcome-hero">'
        '<div class="welcome-kicker">Northstar · Financial crime operations</div>'
        '<h1 class="welcome-title">Review transaction risk.<br><span>Keep every signal in context.</span></h1>'
        '<p class="welcome-copy">A practical AML investigation workspace for reviewing transaction alerts, customer profiles, policy references, and human decisions in one place.</p>'
        f'<div class="welcome-status"><span class="live-dot"></span>{html.escape(upload_text)}</div>'
        '</section>',
        unsafe_allow_html=True,
    )
    def open_dashboard() -> None:
        st.session_state["workspace_navigation_v3"] = "Alerts"

    st.button(
        "Open the operations dashboard",
        type="primary",
        key="welcome_open_dashboard",
        on_click=open_dashboard,
    )

    st.markdown('<div class="section-head"><div class="section-title">Your investigation workspace</div></div>', unsafe_allow_html=True)
    features = [
        ("01 · Import", "Load transaction and customer/KYC CSV files, or extract one transaction from a text-based PDF."),
        ("02 · Analyze", "Run explainable rules, risk scoring, customer checks, and local policy retrieval across a batch."),
        ("03 · Review", "Filter alerts, inspect supporting evidence, record human decisions, and download investigation reports."),
    ]
    feature_cols = st.columns(3)
    for column, (title, description) in zip(feature_cols, features):
        with column:
            st.markdown(
                '<div class="welcome-feature">'
                f'<div class="welcome-step">{html.escape(title)}</div>'
                f'<p>{html.escape(description)}</p></div>',
                unsafe_allow_html=True,
            )
    st.caption(
        "This is an educational demonstration using synthetic data and illustrative AML rules. "
        "It does not make a legal or suspicious-activity determination."
    )


def go_to_data_import() -> None:
    """Navigate from the empty alert queue using Streamlit's callback phase."""
    st.session_state["workspace_navigation_v3"] = "Data import"


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            '<div style="padding: 8px 0 24px">'
            '<div class="brand-mark">NORTHSTAR</div>'
            '<div class="brand-sub">Financial crime operations</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.caption("WORKSPACE")
        if "workspace_navigation_v3" not in st.session_state:
            st.session_state["workspace_navigation_v3"] = "Alerts"
        page = st.radio(
            "Workspace navigation",
            ["Alerts", "Cases", "Customers", "Data import"],
            label_visibility="collapsed",
            key="workspace_navigation_v3",
        )
        st.markdown("---")
        st.caption("DEMO ENVIRONMENT")
        st.markdown("Synthetic transaction dataset")
        st.caption(f"Database: {DB_PATH.name}")
    return page


def render_review_table(rows: list[dict]) -> None:
    if not rows:
        st.info("No transactions match the selected filters.")
        return

    body = []
    for row in rows:
        risk_class = f'badge-{row["risk"].lower()}'
        outcome = {
            "no_rule_flags": "No review required",
            "auto_cleared_below_threshold": "Review not required",
            "pending_human_review": "Awaiting review",
            "closed_no_action": "Closed — no further action",
            "escalated_for_review": "Escalated",
            "human_approved": "Legacy demo approval",
            "human_rejected": "Legacy demo rejection",
        }.get(row["outcome"], row["outcome"].replace("_", " ").title())
        # Older demo uploads may contain pending cases created before routing
        # was restricted to High risk. They remain visible as transactions,
        # but are no longer presented as needing review.
        if row["risk"] != "High" and row["outcome"] == "pending_human_review":
            outcome = "Review not required"
        review_reason = row["flag_label"].replace("No rule flags", "No review indicator")
        body.append(
            "<tr>"
            f'<td><span class="table-id">{html.escape(row["alert_id"] or row["transaction_id"])}</span></td>'
            f'<td>{html.escape(row["customer_name"])}</td>'
            f'<td>{html.escape(row["date_label"])}</td>'
            f'<td>{html.escape(row["amount_label"])}</td>'
            f'<td><span class="badge {risk_class}">{html.escape(row["risk"])}</span></td>'
            f'<td>{html.escape(review_reason)}</td>'
            f'<td>{html.escape(outcome)}</td>'
            f'<td>{html.escape(row["decision"].title())}</td>'
            "</tr>"
        )
    st.markdown(
        '<div class="data-table-wrap"><table class="data-table">'
        '<thead><tr><th>Alert / transaction</th><th>Customer</th><th>Date / time</th>'
        '<th>Amount</th><th>Risk</th><th>Review reason</th><th>Review status</th>'
        '<th>Disposition</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def render_bar_chart(values: dict[str, int], color: str) -> None:
    if not any(values.values()):
        st.caption("Chart data will appear after an upload is analyzed.")
        return
    maximum = max(values.values(), default=1) or 1
    risk_colors = {"High": "#e63389", "Medium": "#ff7545", "Low": "#20b9a1"}
    rows = []
    for label, value in values.items():
        bar_color = risk_colors.get(label, color)
        width = value / maximum * 100
        rows.append(
            '<div class="chart-row">'
            f'<div>{html.escape(label)}</div>'
            '<div class="chart-track">'
            f'<div class="chart-fill" style="width:{width:.2f}%;background:{bar_color}"></div>'
            '</div>'
            f'<div style="text-align:right;color:#f2f5f8;font-weight:700">{value:,}</div>'
            '</div>'
        )
    st.markdown(
        '<div class="chart-panel">' + "".join(rows) + '</div>',
        unsafe_allow_html=True,
    )


def render_outcome_summary(rows: list[dict]) -> None:
    """Show review outcomes from the currently selected upload."""
    outcomes = [
        ("Passed", sum(row["outcome"] in {"no_rule_flags", "auto_cleared_below_threshold"} for row in rows), "#20b9a1"),
        ("Awaiting review", sum(row["outcome"] == "pending_human_review" for row in rows), "#ffb547"),
        ("Closed — no further action", sum(row["outcome"] == "closed_no_action" for row in rows), "#39a6ff"),
        ("Escalated for review", sum(row["outcome"] == "escalated_for_review" for row in rows), "#e63389"),
        ("Legacy demo decisions", sum(row["outcome"] in {"human_approved", "human_rejected"} for row in rows), "#9b8afb"),
    ]
    total = len(rows)
    if not total:
        st.info("Review outcomes will appear after transactions are analyzed.")
        return

    stops = []
    current = 0.0
    for _, count, color in outcomes:
        if count:
            end = current + count / total * 100
            stops.append(f"{color} {current:.2f}% {end:.2f}%")
            current = end
    segments = ", ".join(stops) or "#405265 0% 100%"
    legend = "".join(
        '<div class="outcome-legend-row">'
        f'<span class="outcome-dot" style="background:{color}"></span>'
        f'<span>{html.escape(label)}</span><strong style="margin-left:auto">{count:,}</strong>'
        '</div>'
        for label, count, color in outcomes
    )
    st.markdown(
        '<div class="chart-panel outcome-layout">'
        f'<div class="outcome-donut" style="background:conic-gradient({segments})">'
        f'<div class="outcome-donut-hole">{total:,}<span>transactions</span></div></div>'
        f'<div class="outcome-legend">{legend}</div></div>',
        unsafe_allow_html=True,
    )


def render_activity_trend(rows: list[dict]) -> None:
    currencies = {row["currency"] for row in rows}
    show_amounts = len(currencies) == 1
    daily_values: dict[str, float] = {}
    for row in rows:
        day = row["timestamp"].date().isoformat()
        value = row["amount_value"] if show_amounts else 1
        daily_values[day] = daily_values.get(day, 0) + value
    trend_data = [
        {"Date": day, "Value": value}
        for day, value in sorted(daily_values.items())
    ]
    if not trend_data:
        st.caption("Transaction activity will appear after an upload is analyzed.")
        return
    width, height = 680, 220
    left, right, top, bottom = 38, 14, 14, 38
    plot_width, plot_height = width - left - right, height - top - bottom
    max_value = max(item["Value"] for item in trend_data) or 1
    points = []
    for index, item in enumerate(trend_data):
        x = left + (plot_width * index / max(len(trend_data) - 1, 1))
        y = top + plot_height - (plot_height * item["Value"] / max_value)
        points.append((x, y, item))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in points)
    area_points = (
        f"{points[0][0]:.1f},{top+plot_height} " + polyline
        + f" {points[-1][0]:.1f},{top+plot_height}"
    )

    def axis_label(value: float) -> str:
        if show_amounts:
            if value >= 1_000_000:
                return f"{value/1_000_000:.1f}m"
            if value >= 1_000:
                return f"{value/1_000:.0f}k"
        return f"{value:.0f}"

    grid = []
    for step in range(3):
        y = top + plot_height * step / 2
        label = axis_label(max_value * (2 - step) / 2)
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" '
            'stroke="#405265" stroke-width="1" />'
            f'<text x="{left-9}" y="{y+4:.1f}" text-anchor="end" '
            'font-size="11" fill="#aab8c7">'
            f'{label}</text>'
        )
    dots = []
    for x, y, item in points:
        date_label = datetime.fromisoformat(item["Date"]).strftime("%d %b")
        dots.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#e63389">'
            f'<title>{date_label}: {item["Value"]:,.2f} {next(iter(currencies)) if show_amounts else "transactions"}</title></circle>'
        )
    first_label = datetime.fromisoformat(trend_data[0]["Date"]).strftime("%d %b")
    last_label = datetime.fromisoformat(trend_data[-1]["Date"]).strftime("%d %b")
    svg = (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        'aria-label="Daily transaction volume" style="width:100%;height:auto">'
        + "".join(grid)
        + f'<polygon points="{area_points}" fill="#e63389" fill-opacity=".20" />'
        + f'<polyline points="{polyline}" fill="none" stroke="#e63389" '
        'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
        + "".join(dots)
        + f'<text x="{left}" y="{height-8}" font-size="11" fill="#aab8c7">{first_label}</text>'
        + f'<text x="{width-right}" y="{height-8}" text-anchor="end" '
        f'font-size="11" fill="#aab8c7">{last_label}</text></svg>'
    )
    st.markdown(svg, unsafe_allow_html=True)


def report_text_for_download(row: dict) -> str:
    """Use a generated report, or build a readable fallback for older pending cases."""
    saved_report = row.get("report") or ""
    if saved_report.strip():
        policy_analysis = row.get("policy_analysis", {})
        if policy_analysis.get("mode") == "search_only":
            searches = [
                entry for entry in policy_analysis.get("search_trace", [])
                if entry.get("status") == "searched"
            ]
            appendix = [
                "\n\n## On-demand policy search",
                f'- Status: {policy_analysis.get("search_status", "unknown")}',
            ]
            appendix.extend(
                f'- Search query: {entry.get("query", "")}; '
                f'retrieved policy sections: {", ".join(entry.get("result_policy_ids", [])) or "none"}'
                for entry in searches
            )
            return saved_report.rstrip() + "\n" + "\n".join(appendix)
        return saved_report

    outcome_labels = {
        "no_rule_flags": "No review required",
        "auto_cleared_below_threshold": "Passed — below high-risk threshold",
        "pending_human_review": "Awaiting human review",
        "closed_no_action": "Closed — no further action",
        "escalated_for_review": "Escalated for further review",
        "human_approved": "Legacy demo approval (historical)",
        "human_rejected": "Legacy demo rejection (historical)",
    }
    findings = "\n".join(f"- {finding}" for finding in row["flags"]) or "- No review indicators recorded"
    policy_lines = "\n".join(
        f'- {item["title"]} ({item["policy_id"]}): {item["excerpt"]}'
        for item in row["policy_references"]
    ) or "- No matching policy passage was retrieved"
    evidence_lines = []
    for evidence in row["evidence"]:
        evidence_lines.append(
            f'- Source: {evidence["source_file"]}; record: '
            f'{evidence.get("source_locator") or "not specified"}'
        )
        try:
            fields = json.loads(evidence["excerpt"])
        except (TypeError, json.JSONDecodeError):
            fields = None
        if isinstance(fields, dict):
            evidence_lines.extend(f"  - {key.replace('_', ' ').title()}: {value}" for key, value in fields.items())
        elif evidence.get("excerpt"):
            evidence_lines.append(f'  - {evidence["excerpt"]}')
    evidence_text = "\n".join(evidence_lines) or "- No source evidence was stored"

    human_decision = (
        "Pending human review"
        if row["outcome"] == "pending_human_review"
        else row["decision"]
    )
    return f"""# AML Transaction Investigation

## Transaction
- ID: {row['transaction_id']}
- Date: {row['date_label']}
- Amount: {row['amount_label']}
- Sender: {row['sender']}
- Beneficiary: {row['beneficiary']}
- Channel: {row['channel']}
- Description: {row['description']}

## Customer
- Name: {row['customer_name']}
- Customer ID: {row['customer_id']}
- Country: {row['country']}
- Customer risk rating: {row['customer_risk']}

## Review summary
- Risk level: {row['risk']}
- Illustrative risk score: {row['risk_score']:.2f}
- Status: {outcome_labels.get(row['outcome'], row['outcome'].replace('_', ' ').title())}
- Human decision: {human_decision}
- Reviewer: {row.get('reviewer') or 'Not recorded'}
- Decision rationale: {row.get('decision_rationale') or 'Not recorded'}
- Review findings:
{findings}

## Case
- Case ID: {row['case_id'] or 'No case opened'}
- Alert ID: {row['alert_id'] or 'No alert created'}
- Case status: {row['case_status']}

## Related policy guidance
{policy_lines}

## Source evidence
{evidence_text}

This report summarizes illustrative demo analysis. It is not a determination that activity is suspicious.
"""


def record_human_decision(
    pending_case: dict, decision: str, rationale: str, reviewer: str
) -> None:
    """Resume a paused graph after a human reviewer records a decision."""
    try:
        result = graph.invoke(
            Command(resume={
                "decision": decision,
                "rationale": rationale.strip(),
                "reviewer": reviewer.strip() or "demo_reviewer",
            }),
            config=pending_case["config"],
        )
        saved_policy = load_policy_investigation(
            pending_case["transaction_id"]
        )
        if saved_policy is not None:
            result["policy_references"] = saved_policy.get("references", [])
            result["policy_analysis"] = saved_policy.get("analysis", {})
            result["policy_agent_log"] = result["policy_analysis"].get(
                "search_trace", []
            )
            result["policy_agent_status"] = result["policy_analysis"].get(
                "search_status", "finished"
            )
            result["report"] = generate_report(result)["report"]
        save_case(result)
        record_case_event(
            pending_case["transaction_id"],
            result.get("case", {}).get("case_id"),
            "case_disposition_recorded",
            reviewer.strip() or "demo_reviewer",
            {"decision": decision, "rationale": rationale.strip()},
        )
    except Exception as error:
        st.error(f"Could not record the {decision} decision: {error}")
        return

    thread_id = pending_case["thread_id"]
    st.session_state["pending_reviews"] = [
        item for item in st.session_state.get("pending_reviews", [])
        if item["thread_id"] != thread_id
    ]
    load_reviews.clear()
    last_import = st.session_state.get("last_import_summary")
    if last_import is not None:
        batch_ids = set(last_import.get("transaction_ids", []))
        updated_reviews = load_reviews()
        last_import["pending"] = sum(
            row["transaction_id"] in batch_ids
            and row["outcome"] == "pending_human_review"
            for row in updated_reviews
        )
    decision_label = (
        "closed with no further action"
        if decision == "close_no_action"
        else "escalated for further review"
    )
    st.session_state["decision_notice"] = (
        f'{pending_case["transaction_id"]} was {decision_label}.'
    )
    st.rerun()


def render_human_review_controls(
    row: dict, pending_case: dict, key_suffix: str
) -> None:
    st.markdown("#### Human case disposition")
    st.caption(
        "Record what should happen to this alert and why. This demo records a case disposition; it does not approve or block the payment."
    )
    form_col, agent_col = st.columns([2.2, 1])
    with form_col:
        with st.form(f'case_disposition_{row["transaction_id"]}_{key_suffix}'):
            decision = st.selectbox(
                "Disposition",
                ["close_no_action", "escalate"],
                format_func=lambda value: {
                    "close_no_action": "Close alert — no further action",
                    "escalate": "Escalate for further review",
                }[value],
            )
            rationale = st.text_area(
                "Reviewer rationale (required)",
                placeholder="Summarize the facts reviewed and why this disposition is appropriate.",
                height=90,
            )
            reviewer = st.text_input(
                "Reviewer name (demo only)", value="Demo reviewer"
            )
            submitted = st.form_submit_button(
                "Record case disposition", type="primary", use_container_width=True
            )
        if submitted:
            if len(rationale.strip()) < 10:
                st.warning("Enter a brief rationale of at least 10 characters.")
            elif not reviewer.strip():
                st.warning("Enter the reviewer name for this demo record.")
            else:
                record_human_decision(pending_case, decision, rationale, reviewer)
    with agent_col:
        st.markdown("#### Optional policy research")
        st.caption("Search the local demo policy. The agent cannot decide the case.")
        running = policy_agent_job_running(row["transaction_id"])
        if st.button(
            "Run policy search",
            key=f'run_policy_agent_{row["transaction_id"]}_{key_suffix}',
            help="At most one local policy search; results are saved to this case.",
            disabled=running,
            use_container_width=True,
        ):
            if submit_policy_agent_for_case(row):
                st.info("Policy search started. You can switch tabs while it runs.")
            else:
                st.info("A policy search is already running for this case.")


def render_detail(row: dict, key_suffix: str = "detail") -> None:
    st.markdown("### Investigation detail")
    job_status = policy_agent_job_status(row["transaction_id"])
    if job_status and job_status["status"] == "running":
        st.info(
            "Policy search is running in the background for this case. "
            "You can switch tabs; the result will be saved when it finishes."
        )
    elif job_status and job_status["status"] == "finished":
        load_reviews.clear()
        refreshed_row = next(
            (
                item for item in load_reviews()
                if item["transaction_id"] == row["transaction_id"]
            ),
            None,
        )
        if refreshed_row:
            row.update(refreshed_row)
        if job_status.get("ok"):
            st.success("Policy search finished and was saved to this case.")
        else:
            st.error(f'Policy search failed: {job_status.get("error", "unknown error")}')

    outcome_messages = {
        "no_rule_flags": "No demo rules requested a review for this transaction.",
        "auto_cleared_below_threshold": "Passed automatically: this transaction scored below High risk. Any rule findings remain in the case evidence for context.",
        "pending_human_review": "This transaction is waiting for a human reviewer.",
        "closed_no_action": "The alert was closed with no further action recorded.",
        "escalated_for_review": "This case was escalated for further review.",
        "human_approved": "Historical legacy demo decision: the transaction was marked approved under the older demo workflow.",
        "human_rejected": "Historical legacy demo decision: the transaction was marked rejected under the older demo workflow.",
    }
    outcome_message = outcome_messages.get(
        row["outcome"], row["outcome"].replace("_", " ").title()
    )
    if row["risk"] != "High" and row["outcome"] == "pending_human_review":
        outcome_message = "Human review is not required because this transaction is below High risk."
    if row["outcome"] == "pending_human_review" and row["risk"] == "High":
        st.warning(outcome_message)
        pending_case = next(
            (
                item for item in st.session_state.get("pending_reviews", [])
                if item["transaction_id"] == row["transaction_id"]
            ),
            None,
        )
        if pending_case is not None:
            render_human_review_controls(row, pending_case, key_suffix)
        else:
            st.caption("This pending case must be resumed from the active review queue.")
    elif row["outcome"] == "escalated_for_review":
        st.warning(outcome_message)
    elif row["outcome"] == "auto_cleared_below_threshold" or (
        row["risk"] != "High" and row["outcome"] == "pending_human_review"
    ):
        st.success(outcome_message)
    elif row["outcome"] == "human_rejected":
        st.error(outcome_message)
    else:
        st.success(outcome_message)

    id_col, amount_col, risk_col = st.columns([1.05, 1.3, 1])
    id_col.metric("Transaction ID", row["transaction_id"])
    amount_col.metric("Amount", row["amount_label"])
    risk_col.metric(
        "Risk level", f'{row["risk"]} · {row["risk_score"]:.2f}'
    )
    st.caption(f'{row["date_label"]}  |  {row["channel"].title()} payment')

    finding_sources = [("Transaction rules", item) for item in row["flags"]]
    finding_sources.extend(
        ("Transaction review", item)
        for item in _report_list(row["report"], "Transaction specialist findings")
    )
    finding_sources.extend(
        ("Customer profile review", item)
        for item in _report_list(row["report"], "Customer specialist findings")
    )

    # Group differently worded versions of the same amount threshold finding.
    grouped_findings: dict[str, dict[str, object]] = {}
    for source, finding in finding_sources:
        normalized = finding.casefold()
        is_amount_threshold = (
            ("review limit" in normalized or "threshold" in normalized)
            and ("amount" in normalized or "transaction exceeds" in normalized)
        )
        key = "amount_threshold" if is_amount_threshold else normalized
        display = (
            "Amount is above the demo review threshold"
            if is_amount_threshold else finding
        )
        group = grouped_findings.setdefault(
            key, {"display": display, "sources": []}
        )
        if source not in group["sources"]:
            group["sources"].append(source)

    transaction_findings = _report_list(row["report"], "Transaction specialist findings")
    customer_findings = _report_list(row["report"], "Customer specialist findings")
    st.markdown(
        "#### Review findings"
    )
    specialist_cols = st.columns(4)
    specialist_cards = [
        ("Compliance indicators", row["flags"]),
        ("Transaction indicators", transaction_findings),
        ("Customer / KYC indicators", customer_findings),
        ("Risk level", [f'{row["risk"]} · {row["risk_score"]:.2f}']),
    ]
    for column, (title, findings) in zip(specialist_cols, specialist_cards):
        with column:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                if findings:
                    st.write(" · ".join(findings[:2]))
                    if len(findings) > 2:
                        st.caption(f"+{len(findings) - 2} more finding(s)")
                else:
                    st.write("None identified")

    auto_cleared = row["outcome"] == "auto_cleared_below_threshold"
    st.markdown(
        "**Signals retained for context**" if auto_cleared
        else "**Combined reasons for review**"
    )
    if grouped_findings:
        for finding in grouped_findings.values():
            st.markdown(f'• {finding["display"]}')
            st.caption("Identified by: " + ", ".join(finding["sources"]))
    else:
        st.write("No compliance or specialist findings were recorded.")

    customer_col, parties_col = st.columns(2)
    with customer_col:
        st.markdown("#### Customer profile")
        st.write(f'**{row["customer_name"]}** ({row["customer_id"]})')
        st.write(f'Country: {row["country"]}')
        st.write(f'Customer risk rating: {row["customer_risk"]}')
    with parties_col:
        st.markdown("#### Payment details")
        st.write(f'**Sender:** {row["sender"]}')
        st.write(f'**Beneficiary:** {row["beneficiary"]}')
        st.write(f'**Description:** {row["description"]}')

    with st.container(border=True):
        st.markdown("#### Related customer activity")
        st.caption(
            "30-day view from transactions analyzed in this upload only; "
            "it is not a complete account history."
        )
        cutoff = row["timestamp"] - timedelta(days=30)
        activity_rows = [
            item for item in dashboard_reviews
            if item["customer_id"] == row["customer_id"]
            and (not row.get("account_id") or item.get("account_id") == row.get("account_id"))
            and cutoff <= item["timestamp"] <= row["timestamp"]
        ]
        if not any(item["transaction_id"] == row["transaction_id"] for item in activity_rows):
            activity_rows.append(row)
        totals_by_currency: dict[str, float] = {}
        for item in activity_rows:
            totals_by_currency[item["currency"]] = (
                totals_by_currency.get(item["currency"], 0.0) + item["amount_value"]
            )
        total_label = " · ".join(
            f"{currency} {amount:,.0f}"
            for currency, amount in sorted(totals_by_currency.items())
        )
        activity_metrics = st.columns(4)
        activity_metrics[0].metric("Transactions in 30 days", len(activity_rows))
        activity_metrics[1].metric("Value in 30 days", total_label or "—")
        activity_metrics[2].metric(
            "Beneficiaries", len({item["beneficiary"] for item in activity_rows})
        )
        expected_turnover = row["_customer"].get("expected_monthly_turnover_usd")
        if expected_turnover and set(totals_by_currency) == {"USD"}:
            ratio = totals_by_currency["USD"] / float(expected_turnover)
            activity_metrics[3].metric(
                "Of expected monthly turnover", f"{ratio:.0%}"
            )
        else:
            activity_metrics[3].metric("Of expected turnover", "N/A")
        if row.get("account_id"):
            st.caption(f'Account reference: {row["account_id"]}')
        recent_activity = sorted(
            activity_rows, key=lambda item: item["timestamp"], reverse=True
        )[:8]
        activity_rows_html = "".join(
            "<tr>"
            f'<td>{html.escape(item["date_label"])}</td>'
            f'<td><span class="table-id">{html.escape(item["transaction_id"])}</span></td>'
            f'<td>{html.escape((item.get("direction") or "unknown").title())}</td>'
            f'<td>{html.escape(item["beneficiary"])}</td>'
            f'<td>{html.escape(item["amount_label"])}</td>'
            "</tr>"
            for item in recent_activity
        )
        st.markdown(
            '<div class="data-table-wrap"><table class="data-table">'
            '<thead><tr><th>Date / time</th><th>Transaction</th><th>Flow</th>'
            '<th>Beneficiary</th><th>Amount</th></tr></thead>'
            f'<tbody>{activity_rows_html}</tbody></table></div>',
            unsafe_allow_html=True,
        )

    with st.expander("Risk score details"):
        st.caption(row["rationale"])
        if row["indicators"]:
            st.markdown("**Factors included in the score**")
            for indicator in row["indicators"]:
                st.markdown(f"- {indicator}")
        else:
            st.write("No additional risk indicators were recorded.")
        st.info(
            "The score and thresholds are illustrative demo logic. "
            "They are not a determination that the activity is suspicious."
        )

    with st.expander("Source evidence"):
        if not row["evidence"]:
            st.caption("No structured evidence was stored for this older record.")
        for evidence in row["evidence"]:
            st.markdown(
                f'**{evidence["evidence_id"]}**  |  {evidence["source_file"]} '
                f'| Record {evidence.get("source_locator") or "Not specified"}'
            )
            try:
                source_fields = json.loads(evidence["excerpt"])
            except (TypeError, json.JSONDecodeError):
                source_fields = None

            if isinstance(source_fields, dict):
                for key, value in source_fields.items():
                    field_col, value_col = st.columns([1, 3])
                    field_col.caption(key.replace("_", " ").title())
                    value_col.write(str(value))
            else:
                st.write(evidence["excerpt"])

    if row["policy_references"]:
        with st.expander(f'Policy references ({len(row["policy_references"])})'):
            st.caption(
                "Retrieved passages from the fictional demo policy. Check whether "
                "each passage applies to this alert; retrieval alone does not make it relevant."
            )
            for index, policy in enumerate(row["policy_references"]):
                st.markdown(f'**{policy["title"]}**')
                st.caption(
                    f'{policy["policy_id"]}  |  {policy["source_file"]}  |  '
                    f'{policy.get("retrieval_method", "local search")}'
                )
                st.write(policy["excerpt"])
                if index < len(row["policy_references"]) - 1:
                    st.divider()
    else:
        with st.expander("Policy references"):
            st.caption("No policy passages were retrieved for this case.")

    analysis = row["policy_analysis"]
    if analysis or row["outcome"] != "no_rule_flags":
        with st.expander("Policy investigation"):
            st.caption(
                "Optional research aid for human reviewers. It searches the local "
                "demo policy at most once and does not make the case decision."
            )
            search_trace = analysis.get("search_trace", [])
            if search_trace:
                st.markdown("**Policy investigation agent**")
                for attempt, item in enumerate(
                    (
                        entry
                        for entry in search_trace
                        if entry.get("status") == "searched"
                    ),
                    start=1,
                ):
                    st.caption(
                        f'Pass {attempt}: searched “{item.get("query", "")}” — '
                        f'{item.get("result_count", 0)} result(s), '
                        f'{len(item.get("new_policy_ids", []))} new section(s).'
                    )
                if not any(item.get("status") == "searched" for item in search_trace):
                    st.caption(
                        "Policy search agent status: "
                        f'{analysis.get("search_status", "not run")}.'
                    )
            elif analysis.get("search_status"):
                st.caption(
                    "Policy search agent status: "
                    f'{analysis["search_status"]}.'
                )
            if analysis.get("mode") == "search_only":
                st.caption("Search-only agent run; the reviewer evaluates the retrieved passages.")
            elif analysis.get("model"):
                if analysis.get("model_error"):
                    st.caption(
                        "AI interpretation could not be completed; retrieved "
                        "policy passages remain available for review."
                    )
                else:
                    st.caption(
                        "AI-assisted interpretation of fictional demo policy text; "
                        "reviewers should verify it against the approved policy source."
                    )
            else:
                st.caption(
                    "AI interpretation was not run for this upload. Retrieved "
                    "policy passages remain available above for review."
                )
            st.write(analysis.get("summary", "No summary available."))
            for finding in analysis.get("findings", []):
                st.markdown(f'**{finding["policy_id"]}:** {finding["observation"]}')
                st.markdown(f'> {finding["supporting_quote"]}')
            for question in analysis.get("open_questions", []):
                st.markdown(f"- Reviewer question: {question}")

    with st.expander("Case timeline"):
        if not row["case_id"]:
            st.write("No case was opened for this transaction.")
        else:
            st.write(f'**Case:** {row["case_id"]}  |  Status: {row["case_status"].title()}')
            st.write(f'**Alert:** {row["alert_id"]}')
            event_labels = {
                "case_opened": "Case opened",
                "policy_search_completed": "Policy research completed",
                "policy_search_failed": "Policy research failed",
                "case_disposition_recorded": "Reviewer disposition recorded",
            }
            events = load_case_events(row["transaction_id"])
            if events:
                for event in events:
                    event_time = datetime.fromisoformat(event["occurred_at"])
                    st.markdown(
                        f'**{event_labels.get(event["event_type"], event["event_type"].replace("_", " ").title())}** '
                        f'· {event_time.strftime("%d %b %Y, %H:%M UTC")} · {event["actor"]}'
                    )
                    details = event.get("details", {})
                    if event["event_type"] == "case_opened":
                        st.caption("Review reasons: " + "; ".join(details.get("review_reasons", [])))
                    elif event["event_type"] == "case_disposition_recorded":
                        st.caption(
                            f'{_decision_label(details.get("decision"), row["outcome"])} — '
                            f'{details.get("rationale", "")}'
                        )
                    elif event["event_type"].startswith("policy_search"):
                        st.caption(
                            f'Status: {details.get("status", "error")} · '
                            f'Policy sections: {", ".join(details.get("policy_ids", [])) or "none"}'
                        )
            else:
                st.caption("No detailed event history exists for this older case record.")

    st.download_button(
        "Download investigation report",
        data=report_text_for_download(row),
        file_name=f'{row["transaction_id"]}_investigation.md',
        mime="text/markdown",
        key=f'investigation_report_{row["transaction_id"]}_{key_suffix}',
    )

def uploaded_customers(file_bytes: bytes) -> dict[str, Customer]:
    text = file_bytes.decode("utf-8-sig")
    customers: dict[str, Customer] = {}
    for row in csv.DictReader(io.StringIO(text)):
        customer = Customer.model_validate(row)
        customers[customer.customer_id] = customer
    if not customers:
        raise ValueError("The customer CSV has no data rows.")
    return customers


def queue_or_save_result(
    result: dict,
    transaction_id: str,
    customer_name: str,
    config: dict,
) -> str:
    if result.get("__interrupt__"):
        # Persist the open case and pending outcome before presenting it in the UI.
        if not result.get("report"):
            pending_state = {**result, "human_decision": "Pending human review"}
            result["report"] = generate_report(pending_state)["report"]
        save_case(result)
        record_case_event(
            transaction_id,
            result.get("case", {}).get("case_id"),
            "case_opened",
            "system",
            {"review_reasons": result.get("review_reasons", [])},
        )
        pending = st.session_state.setdefault("pending_reviews", [])
        pending.append(
            {
                "transaction_id": transaction_id,
                "customer_name": customer_name,
                "thread_id": config["configurable"]["thread_id"],
                "config": config,
                "review_reasons": result.get("review_reasons", []),
            }
        )
        return "Pending human review"

    save_case(result)
    return result["workflow_outcome"].replace("_", " ").title()


def analyze_uploaded_transaction(
    transaction: AMLTransaction,
    customer: Customer,
    source_file: str,
    source_text: str,
    thread_id: str,
) -> str:
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {
            "raw_transaction": transaction.model_dump(mode="json"),
            "raw_customer": customer.model_dump(mode="json"),
            "source_file": source_file,
            "source_text": source_text,
        },
        config=config,
    )
    return queue_or_save_result(
        result, transaction.transaction_id, customer.legal_name, config
    )


def render_import_page() -> None:
    st.markdown('<div class="section-head"><div class="section-title">Import source files</div></div>', unsafe_allow_html=True)
    last_import = st.session_state.get("last_import_summary")
    if last_import:
        st.success(
            f'Last import: {last_import["processed"]} analyzed, '
            f'{last_import["pending"]} awaiting human review, '
            f'{last_import["error_count"]} row errors.'
        )
        for error in last_import["errors"][:20]:
            st.error(error)
    st.caption(
        "Upload a customer/KYC CSV and a transaction CSV, or a single-transaction PDF. "
        "Each record is validated before analysis."
    )
    customer_file = st.file_uploader(
        "Customer and KYC profiles (CSV)", type=["csv"], key="upload_customers"
    )
    transaction_file = st.file_uploader(
        "Transactions (CSV)", type=["csv"], key="upload_transactions"
    )
    customers: dict[str, Customer] = {}
    if customer_file is not None:
        try:
            customers = uploaded_customers(customer_file.getvalue())
            st.success(f"Loaded {len(customers)} customer profiles from the upload.")
        except Exception as error:
            st.error(f"Could not read customer CSV: {error}")

    if customers and transaction_file is not None:
        batch_limit = st.number_input(
            "Maximum transactions to analyze (0 = all)",
            min_value=0,
            max_value=10000,
            value=5,
            step=5,
        )
        if st.button("Validate and analyze CSV batch", type="primary"):
            rows = list(
                csv.DictReader(
                    io.StringIO(transaction_file.getvalue().decode("utf-8-sig"))
                )
            )
            rows_to_process = rows if batch_limit == 0 else rows[:batch_limit]
            processed = 0
            pending = 0
            processed_ids = []
            errors = []
            upload_tag = str(abs(hash(transaction_file.name)))
            progress = st.progress(0.0, text="Preparing transactions")

            for index, original_row in enumerate(rows_to_process, start=1):
                row = dict(original_row)
                customer_id = row.pop("customer_id", "").strip()
                customer = customers.get(customer_id)
                try:
                    if customer is None:
                        raise ValueError(f"No uploaded customer profile for {customer_id!r}")
                    transaction = AMLTransaction.model_validate(row)
                    evidence_text = json.dumps(
                        {**row, "customer_id": customer_id}, ensure_ascii=False
                    )
                    status = analyze_uploaded_transaction(
                        transaction,
                        customer,
                        transaction_file.name,
                        evidence_text,
                        f"upload-{upload_tag}-{transaction.transaction_id}",
                    )
                    processed += 1
                    processed_ids.append(transaction.transaction_id)
                    pending += status == "Pending human review"
                except Exception as error:
                    errors.append(f"Row {index}: {error}")
                progress.progress(
                    index / max(len(rows_to_process), 1),
                    text=f"Analyzed {index} of {len(rows_to_process)} rows",
                )

            st.session_state["last_import_summary"] = {
                "processed": processed,
                "transaction_ids": processed_ids,
                "pending": pending,
                "error_count": len(errors),
                "errors": errors,
            }
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")
    st.markdown("#### Single transaction PDF")
    pdf_file = st.file_uploader(
        "Transaction document (PDF)", type=["pdf"], key="upload_transaction_pdf"
    )
    if pdf_file is not None:
        try:
            from pypdf import PdfReader
        except ImportError:
            st.warning(
                "PDF text extraction needs the `pypdf` package. The package "
                "download was blocked in this environment. Install it in your "
                "project with `uv add pypdf`, then restart the dashboard."
            )
        else:
            if not customers:
                st.info("Upload the customer/KYC CSV above, then select the matching customer.")
            else:
                customer_id = st.selectbox(
                    "Customer linked to this PDF",
                    sorted(customers),
                    format_func=lambda key: f"{customers[key].legal_name} ({key})",
                )
                if st.button("Extract and analyze PDF", type="primary"):
                    reader = PdfReader(io.BytesIO(pdf_file.getvalue()))
                    pdf_text = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    ).strip()
                    if not pdf_text:
                        st.error("No selectable text found in this PDF. Scanned-image OCR is not configured yet.")
                    else:
                        try:
                            extractor = ChatOllama(
                                model="gemma4:e4b", temperature=0
                            ).with_structured_output(AMLTransaction)
                            transaction = extractor.invoke(
                                "Extract one transaction supported by the PDF text. "
                                "Do not infer missing values. If the required transaction "
                                "identifier or fields are absent, report a validation error. "
                                "If only a date is present, use midnight UTC and treat it "
                                "as a normalization assumption.\n\n"
                                + pdf_text
                            )
                            status = analyze_uploaded_transaction(
                                transaction,
                                customers[customer_id],
                                pdf_file.name,
                                pdf_text,
                                f"pdf-{abs(hash(pdf_file.name))}-{transaction.transaction_id}",
                            )
                            st.cache_data.clear()
                            st.session_state["last_import_summary"] = {
                                "processed": 1,
                                "transaction_ids": [transaction.transaction_id],
                                "pending": int(status == "Pending human review"),
                                "error_count": 0,
                                "errors": [],
                            }
                            st.rerun()
                        except Exception as error:
                            st.error(f"PDF extraction or validation failed: {error}")

    pending_reviews = st.session_state.get("pending_reviews", [])
    if pending_reviews:
        st.markdown("---")
        st.markdown("#### Human review queue")
        selected_thread = st.selectbox(
            "Select pending transaction",
            [item["thread_id"] for item in pending_reviews],
            format_func=lambda thread: next(
                f'{item["transaction_id"]}  |  {item["customer_name"]}'
                for item in pending_reviews
                if item["thread_id"] == thread
            ),
        )
        selected = next(
            item for item in pending_reviews if item["thread_id"] == selected_thread
        )
        st.warning("Review reasons: " + "; ".join(selected["review_reasons"]))
        selected_review = next(
            (
                row for row in load_reviews()
                if row["transaction_id"] == selected["transaction_id"]
            ),
            None,
        )
        if selected_review is not None:
            render_human_review_controls(
                selected_review, selected, f"import_{selected_thread}"
            )
        else:
            st.warning(
                "The saved review is not available for this pending session. "
                "Re-import the transaction file to resume it in this demo."
            )


page = render_sidebar()
running_policy_cases = active_policy_agent_jobs()
if running_policy_cases:
    st.info(
        "Policy search continues in the background for: "
        + ", ".join(running_policy_cases)
        + ". You can use other dashboard tabs while it runs."
    )
reviews = load_reviews()
last_import = st.session_state.get("last_import_summary")

# The dashboard represents the current browser session's analyzed upload.
# Historical SQLite rows remain available to the application, but they should
# not make a fresh dashboard look as if this session already analyzed them.
if last_import is None:
    dashboard_reviews = []
else:
    batch_ids = set(last_import.get("transaction_ids", []))
    dashboard_reviews = [
        row for row in reviews if row["transaction_id"] in batch_ids
    ]

# Older demo records may have been paused for review when any rule flag could
# create a case. Keep those transactions visible, but present them according
# to the current High-risk-only review rule throughout the dashboard.
for row in dashboard_reviews:
    if row["risk"] != "High" and row["outcome"] == "pending_human_review":
        row["outcome"] = "auto_cleared_below_threshold"
        row["decision"] = "Review not required"
        row["case_status"] = "Not required"

st.markdown(
    '<div class="topline"><div><div class="eyebrow">Operations center</div>'
    f'<h1 style="margin:0">{html.escape(page)} workbench</h1>'
    '<div class="page-subtitle">Triage alerts, review case evidence, and record accountable human dispositions.</div></div>'
    f'<div class="live-pill"><span class="live-dot"></span> {"CURRENT UPLOAD" if last_import is not None else "AWAITING UPLOAD"}</div></div>',
    unsafe_allow_html=True,
)

if st.button("Refresh dashboard data"):
    load_reviews.clear()
    st.rerun()

if last_import is None:
    st.info("No transactions analyzed in this session yet. Import customer and transaction files to populate the alert queue.")
else:
    st.caption(
        f"Showing the latest upload · {len(dashboard_reviews):,} analyzed transaction(s)"
    )
decision_notice = st.session_state.pop("decision_notice", None)
if decision_notice:
    st.success(decision_notice)

pending_count = sum(
    row["risk"] == "High" and row["outcome"] == "pending_human_review"
    for row in dashboard_reviews
)
escalated_count = sum(
    row["risk"] == "High" and row["outcome"] == "escalated_for_review"
    for row in dashboard_reviews
)
currency_totals = {
    row["currency"] for row in dashboard_reviews if row.get("currency")
}
alert_rows = [
    row for row in dashboard_reviews
    if row["risk"] == "High" and (
        row["case_id"] or row["outcome"] in {
            "pending_human_review", "closed_no_action", "escalated_for_review",
            "human_approved", "human_rejected",
        }
    )
]
high_alert_count = sum(row["risk"] == "High" for row in alert_rows)

if page in {"Alerts", "Cases"}:
    metric_cols = st.columns(4)
    with metric_cols[0]:
        metric_card("TRANSACTIONS ANALYZED", f"{len(dashboard_reviews):,}")
    with metric_cols[1]:
        metric_card("HIGH-RISK ALERTS", f"{high_alert_count:,}")
    with metric_cols[2]:
        metric_card("AWAITING REVIEW", f"{pending_count:,}")
    with metric_cols[3]:
        metric_card("ESCALATED CASES", f"{escalated_count:,}")

if page == "Alerts":
    st.markdown('<div class="section-head"><div class="section-title">Transactions in this upload</div></div>', unsafe_allow_html=True)
    if not dashboard_reviews:
        st.info("No transactions are available yet. Import a customer/KYC file and transaction file to start an analysis batch.")
        st.button(
            "Go to data import", type="primary", key="alerts_import_cta",
            on_click=go_to_data_import,
        )

    controls = st.columns([2.1, 1, 1, 1])
    with controls[0]:
        search = st.text_input("Search transactions", placeholder="Customer, transaction, or beneficiary", key="alert_search")
    with controls[1]:
        risk_filter = st.selectbox("Risk level", ["All", "High", "Medium", "Low"], key="alert_risk_filter")
    with controls[2]:
        status_options = ["All"] + sorted({row["case_status"].replace("_", " ").title() for row in dashboard_reviews})
        status_filter = st.selectbox("Case status", status_options, key="alert_status_filter")
    with controls[3]:
        sort_order = st.selectbox("Sort by", ["Highest risk", "Newest first", "Largest amount"], key="alert_sort")

    filtered_alerts = list(dashboard_reviews)
    if risk_filter != "All":
        filtered_alerts = [row for row in filtered_alerts if row["risk"] == risk_filter]
    if status_filter != "All":
        filtered_alerts = [row for row in filtered_alerts if row["case_status"].replace("_", " ").title() == status_filter]
    if search:
        term = search.casefold()
        filtered_alerts = [
            row for row in filtered_alerts
            if any(term in value.casefold() for value in (
                row["transaction_id"], row["customer_name"], row["beneficiary"], row["customer_id"]
            ))
        ]
    if sort_order == "Highest risk":
        filtered_alerts.sort(key=lambda row: (row["risk_score"], row["timestamp"]), reverse=True)
    elif sort_order == "Newest first":
        filtered_alerts.sort(key=lambda row: row["timestamp"], reverse=True)
    else:
        filtered_alerts.sort(key=lambda row: row["amount_value"], reverse=True)

    st.caption(f"{len(filtered_alerts):,} transactions shown · {len(dashboard_reviews):,} total in this upload. Only High-risk transactions require review.")
    render_review_table(filtered_alerts)
    if filtered_alerts:
        selected_alert_id = st.selectbox(
            "Open transaction",
            [row["transaction_id"] for row in filtered_alerts],
            format_func=lambda transaction_id: next(
                f'{row["transaction_id"]} · {row["customer_name"]} · {row["amount_label"]}'
                for row in filtered_alerts if row["transaction_id"] == transaction_id
            ),
            key="alerts_selected_case",
        )
        selected_alert = next(row for row in filtered_alerts if row["transaction_id"] == selected_alert_id)
        st.markdown('<div class="section-head"><div class="section-title">Transaction details</div></div>', unsafe_allow_html=True)
        render_detail(selected_alert, key_suffix="alerts")
    elif dashboard_reviews:
        st.success("No transactions match these filters.")

    with st.expander("Portfolio analytics"):
        chart_cols = st.columns(2)
        with chart_cols[0]:
            st.markdown("**Transactions by risk level**")
            risk_counts = {label: sum(row["risk"] == label for row in dashboard_reviews) for label in ["High", "Medium", "Low"]}
            render_bar_chart(risk_counts, "#0c8b83")
        with chart_cols[1]:
            st.markdown("**Daily transaction activity**")
            if len(currency_totals) == 1:
                st.caption(f"Amount · {next(iter(currency_totals))}")
            elif len(currency_totals) > 1:
                st.caption("Transaction count · mixed currencies")
            render_activity_trend(dashboard_reviews)

    export_buffer = io.StringIO()
    export_rows = [
        {"transaction_id": row["transaction_id"], "customer_id": row["customer_id"],
         "customer_name": row["customer_name"], "amount": row["amount_value"],
         "currency": row["currency"], "risk": row["risk"], "risk_score": row["risk_score"],
         "flags": row["flag_label"], "case_status": row["case_status"], "decision": row["decision"]}
        for row in filtered_alerts
    ]
    if export_rows:
        writer = csv.DictWriter(export_buffer, fieldnames=export_rows[0].keys())
        writer.writeheader()
        writer.writerows(export_rows)
        st.download_button("Export filtered alerts", data=export_buffer.getvalue(),
                           file_name="aml_transactions.csv", mime="text/csv", key="export_alert_queue")

elif page == "Cases":
    st.markdown('<div class="section-head"><div class="section-title">Case management</div></div>', unsafe_allow_html=True)
    # Only High-risk records are routed into case review. Older demo records
    # may have cases from the previous flags-based routing behavior.
    case_rows = [
        row for row in dashboard_reviews
        if row["risk"] == "High" and row["case_id"]
    ]
    case_controls = st.columns([2, 1, 1])
    with case_controls[0]:
        case_search = st.text_input("Search cases", placeholder="Case ID, customer, or transaction", key="case_search")
    with case_controls[1]:
        case_statuses = ["All"] + sorted({row["case_status"].replace("_", " ").title() for row in case_rows})
        case_status_filter = st.selectbox("Status", case_statuses, key="case_status_filter")
    with case_controls[2]:
        case_risk_filter = st.selectbox("Risk", ["All", "High", "Medium", "Low"], key="case_risk_filter")
    filtered_cases = list(case_rows)
    if case_status_filter != "All":
        filtered_cases = [row for row in filtered_cases if row["case_status"].replace("_", " ").title() == case_status_filter]
    if case_risk_filter != "All":
        filtered_cases = [row for row in filtered_cases if row["risk"] == case_risk_filter]
    if case_search:
        term = case_search.casefold()
        filtered_cases = [row for row in filtered_cases if any(term in value.casefold() for value in (
            row["case_id"] or "", row["transaction_id"], row["customer_name"], row["customer_id"]
        ))]
    st.caption(f"{len(filtered_cases):,} cases shown · {pending_count:,} awaiting human disposition")
    render_review_table(filtered_cases)
    if filtered_cases:
        selected_case_id = st.selectbox(
            "Open case", [row["transaction_id"] for row in filtered_cases],
            format_func=lambda transaction_id: next(
                f'{row["case_id"]} · {row["customer_name"]} · {row["case_status"].replace("_", " ").title()}'
                for row in filtered_cases if row["transaction_id"] == transaction_id
            ), key="cases_selected_case",
        )
        selected_case = next(row for row in filtered_cases if row["transaction_id"] == selected_case_id)
        render_detail(selected_case, key_suffix="cases")
    else:
        st.info("Cases will appear here when an analyzed transaction meets the demo review criteria.")

elif page == "Customers":
    st.markdown('<div class="section-head"><div class="section-title">Customer activity</div></div>', unsafe_allow_html=True)
    st.caption("Customer and related transaction context from the current upload only.")
    if not dashboard_reviews:
        st.info("Customer activity will populate after you analyze an upload.")
    customer_groups: dict[str, list[dict]] = {}
    for row in dashboard_reviews:
        customer_groups.setdefault(row["customer_id"], []).append(row)
    customer_rows = []
    for customer_id, activity in customer_groups.items():
        first = activity[0]
        customer_rows.append(
            {
                "Customer ID": customer_id,
                "Customer": first["customer_name"],
                "Country": first["country"],
                "Customer risk": first["customer_risk"],
                "Transactions": len(activity),
                "Alerts": sum(bool(row["flags"]) for row in activity),
                "High risk": sum(row["risk"] == "High" for row in activity),
                "Total value": " · ".join(
                    f'{currency} {sum(item["amount_value"] for item in activity if item["currency"] == currency):,.2f}'
                    for currency in sorted({item["currency"] for item in activity})
                ),
            }
        )
    st.caption(f"{len(customer_rows)} customers represented in the analyzed transactions")
    st.markdown('<div class="customer-table-hint">Scroll horizontally to see all customer metrics.</div>', unsafe_allow_html=True)
    customer_table = []
    for row in customer_rows:
        customer_table.append(
            "<tr>"
            f'<td><span class="table-id">{html.escape(row["Customer ID"])}</span></td>'
            f'<td>{html.escape(row["Customer"])}</td>'
            f'<td>{html.escape(row["Country"])}</td>'
            f'<td>{html.escape(row["Customer risk"])}</td>'
            f'<td>{row["Transactions"]}</td><td>{row["Alerts"]}</td>'
            f'<td>{row["High risk"]}</td><td>{html.escape(row["Total value"])}</td>'
            "</tr>"
        )
    st.markdown(
        '<div class="data-table-wrap"><table class="data-table customer-data-table">'
        '<thead><tr><th>Customer ID</th><th>Customer</th><th>Country</th>'
        '<th>Customer risk</th><th>Transactions</th><th>Alerts</th>'
        '<th>High risk</th><th>Total value</th></tr></thead>'
        f'<tbody>{"".join(customer_table)}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    if customer_rows:
        selected_customer_id = st.selectbox(
            "Open customer profile",
            [row["Customer ID"] for row in customer_rows],
            format_func=lambda customer_id: next(
                f'{row["Customer"]} · {customer_id}'
                for row in customer_rows if row["Customer ID"] == customer_id
            ),
            key="customer_profile_selection",
        )
        selected_activity = customer_groups[selected_customer_id]
        customer = selected_activity[0]["_customer"]
        profile_cols = st.columns(4)
        profile_cols[0].metric("Customer risk", customer.get("risk_rating", "—").title())
        profile_cols[1].metric("KYC status", customer.get("kyc_status") or "Not provided")
        profile_cols[2].metric("PEP status", customer.get("pep_status") or "Not provided")
        profile_cols[3].metric("Sanctions screen", customer.get("sanctions_screening_status") or "Not provided")
        st.caption("Profile screening fields are supplied by the uploaded demo file; no external screening service is connected.")
        render_review_table(sorted(selected_activity, key=lambda row: row["timestamp"], reverse=True))
else:
    render_import_page()
