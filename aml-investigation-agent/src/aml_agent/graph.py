from typing import NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from schemas import AMLAlert, AMLCase, AMLTransaction, Customer, EvidenceRecord
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from pathlib import Path
from langchain_ollama import ChatOllama
from datetime import datetime, timezone
import json
from storage import save_case
from risk_tools import assess_transaction
from specialists import (
    customer_specialist,
    policy_agent_decide,
    policy_agent_search,
    policy_analysis_specialist,
    policy_specialist,
    route_policy_agent,
    transaction_specialist,
)



class AMLState(TypedDict):
    raw_transaction: dict
    source_file: str
    source_text: str
    transaction: NotRequired[dict]
    compliance_flags: list[str]
    compliance_status: str
    review_note: NotRequired[str]
    human_decision: NotRequired[str]
    decision_rationale: NotRequired[str]
    reviewer: NotRequired[str]
    workflow_outcome: NotRequired[str]
    risk_assessment: NotRequired[dict]
    transaction_specialist_findings: NotRequired[list[str]]
    customer_specialist_findings: NotRequired[list[str]]
    policy_references: NotRequired[list[dict]]
    policy_analysis: NotRequired[dict]
    run_policy_analysis: NotRequired[bool]
    policy_search_iterations: NotRequired[int]
    policy_agent_log: NotRequired[list[dict]]
    policy_agent_action: NotRequired[str]
    policy_agent_query: NotRequired[str]
    policy_agent_status: NotRequired[str]
    policy_agent_rationale: NotRequired[str]
    evidence: NotRequired[list[dict]]
    review_reasons: NotRequired[list[str]]
    requires_review: NotRequired[bool]
    report: NotRequired[str]
    raw_customer: dict
    customer: NotRequired[dict]
    alert: NotRequired[dict]
    case: NotRequired[dict]


def validate_transaction(state: AMLState) -> dict:
    transaction = AMLTransaction.model_validate(state["raw_transaction"])
    customer = Customer.model_validate(state["raw_customer"])
    source_file = state["source_file"]
    source_type = Path(source_file).suffix.casefold().lstrip(".")
    if source_type not in {"csv", "pdf", "txt"}:
        source_type = "text"
    elif source_type == "txt":
        source_type = "text"

    source_evidence = EvidenceRecord(
        evidence_id=f"EV-{transaction.transaction_id}-SOURCE",
        source_file=source_file,
        source_type=source_type,
        source_locator=transaction.transaction_id,
        excerpt=state["source_text"],
        confidence=1.0 if source_type == "csv" else None,
    )

    return {
        "transaction": transaction.model_dump(mode="json"),
        "customer": customer.model_dump(mode="json"),
        "evidence": [source_evidence.model_dump(mode="json")],
    }

def compliance_check(state: AMLState) -> dict:
    transaction = AMLTransaction.model_validate(state["transaction"])
    flags = []

    if transaction.amount > 10_000:
        flags.append("Transaction exceeds the review limit")

    sender = transaction.sender_name.strip().casefold()
    beneficiary = transaction.beneficiary_name.strip().casefold()

    if sender == beneficiary:
        flags.append("Sender and beneficiary are the same")

    status = "review" if flags else "clear"
    return {
        "compliance_flags": flags,
        "compliance_status": status,
    }


def assess_transaction_risk(state: AMLState) -> dict:
    transaction = AMLTransaction.model_validate(state["transaction"])
    customer = Customer.model_validate(state["customer"])
    assessment = assess_transaction(transaction, customer)
    return {"risk_assessment": assessment.model_dump(mode="json")}


def synthesize_findings(state: AMLState) -> dict:
    reasons = list(state["compliance_flags"])
    reasons.extend(state.get("transaction_specialist_findings", []))
    reasons.extend(state.get("customer_specialist_findings", []))
    high_risk = state["risk_assessment"]["risk_level"] == "high"
    if high_risk:
        reasons.append("Illustrative risk assessment is high")
    reasons = list(dict.fromkeys(reasons))
    # Demo routing policy: only a high risk score creates a human review case.
    # Lower-risk rule findings remain in the report as context and are auto-cleared.
    requires_review = high_risk
    workflow_outcome = (
        "pending_human_review" if high_risk
        else "auto_cleared_below_threshold" if reasons
        else "no_rule_flags"
    )

    return {
        "review_reasons": reasons,
        "requires_review": requires_review,
        "policy_search_iterations": 0,
        "policy_agent_log": [],
        "compliance_status": "flagged" if state["compliance_flags"] else "clear",
        "workflow_outcome": workflow_outcome,
    }

def create_alert_and_case(state: AMLState) -> dict:
    if not state["requires_review"]:
        return {}

    transaction = AMLTransaction.model_validate(state["transaction"])
    customer = state["customer"]

    alert = AMLAlert(
        alert_id=f"ALERT-{transaction.transaction_id}",
        customer_id=customer["customer_id"],
        transaction_ids=[transaction.transaction_id],
        alert_type="rule_based_transaction_review",
        created_at=transaction.timestamp,
    )

    case = AMLCase(
        case_id=f"CASE-{transaction.transaction_id}",
        customer_id=customer["customer_id"],
        alert_ids=[alert.alert_id],
        status="in_review",
        opened_at=transaction.timestamp,
    )

    return {
        "alert": alert.model_dump(mode="json"),
        "case": case.model_dump(mode="json"),
    }
def route_after_analysis(state: AMLState) -> str:
    return "review" if state["requires_review"] else "clear"


def review_case(state: AMLState) -> dict:
    response = interrupt({
        "transaction_id": state["transaction"]["transaction_id"],
        "review_reasons": state["review_reasons"],
        "question": "Record the case disposition and the review rationale.",
    })

    decision = response["decision"].strip().casefold()
    rationale = response.get("rationale", "").strip()
    reviewer = response.get("reviewer", "demo_reviewer").strip()

    if decision not in {"close_no_action", "escalate"}:
        raise ValueError("Decision must be 'close_no_action' or 'escalate'")
    if len(rationale) < 10:
        raise ValueError("A reviewer rationale of at least 10 characters is required")

    case = AMLCase.model_validate(state["case"])
    alert = AMLAlert.model_validate(state["alert"])
    now = datetime.now(timezone.utc)
    close_case = decision == "close_no_action"

    updated_case = case.model_copy(
        update={
            "status": "closed" if close_case else "escalated",
            "decision": decision,
            "decision_rationale": rationale,
            "reviewer": reviewer,
            "closed_at": now if close_case else None,
        }
    )
    updated_alert = alert.model_copy(
        update={"status": "closed" if close_case else "in_review"}
    )

    return {
        "human_decision": decision,
        "decision_rationale": rationale,
        "reviewer": reviewer,
        "workflow_outcome": "closed_no_action" if close_case else "escalated_for_review",
        "case": updated_case.model_dump(mode="json"),
        "alert": updated_alert.model_dump(mode="json"),
    }
def generate_report(state: AMLState) -> dict:
    transaction = state["transaction"]
    customer = state["customer"]
    risk = state["risk_assessment"]
    human_decision = state.get("human_decision", "Not required")

    case = state.get("case")
    policy_analysis = state.get("policy_analysis", {})
    case_section = ""

    if case:
      case_section = (
        "## Case\n"
        f"- Case ID: {case['case_id']}\n"
        f"- Alert ID: {case['alert_ids'][0]}\n"
        f"- Status: {case['status']}\n"
        f"- Decision: {case.get('decision') or 'Pending human review'}\n\n"
    )

    policy_analysis_lines = [
        f'- {item["policy_id"]}: {item["observation"]} '
        f'\n  Supporting quote: "{item["supporting_quote"]}"'
        for item in policy_analysis.get("findings", [])
    ]
    if not policy_analysis_lines:
        policy_analysis_lines = [
            "- No citation-checked policy interpretation was produced; reviewer should consult the approved policy source."
        ]
    policy_reference_lines = [
        f'- {item["policy_id"]} ({item["source_file"]}): {item["title"]}'
        for item in state.get("policy_references", [])
    ] or ["- No relevant local demo policy section retrieved"]
    policy_search_lines = [
        f'- Search {index}: {item.get("query", "")} — '
        f'{item.get("result_count", 0)} result(s); '
        f'new sections: {item.get("new_policy_ids", [])}'
        for index, item in enumerate(
            (entry for entry in state.get("policy_agent_log", []) if entry.get("status") == "searched"),
            start=1,
        )
    ]
    if not policy_search_lines:
        policy_search_lines = [
            f'- Agent status: {state.get("policy_agent_status", "not run")}'
        ]


    report = f"""# AML Transaction Review

## Transaction
- ID: {transaction["transaction_id"]}
- Amount: {transaction["amount"]} {transaction["currency"]}
- Sender: {transaction["sender_name"]}
- Beneficiary: {transaction["beneficiary_name"]}
- Channel: {transaction["channel"]}

## Customer
- ID: {customer["customer_id"]}
- Name: {customer["legal_name"]}
- Country: {customer["country_code"]}
- Customer risk rating: {customer["risk_rating"]}

## Findings
- Compliance flags: {state["compliance_flags"]}
- Risk level: {risk["risk_level"]}
- Risk score: {risk["risk_score"]}
- Review routing: {"Human review required" if state["requires_review"] else "Passed automatically; below High risk"}
- {"Review reasons" if state["requires_review"] else "Signals retained for context"}: {state["review_reasons"]}
- Transaction specialist findings: {state.get("transaction_specialist_findings", [])}
- Customer specialist findings: {state.get("customer_specialist_findings", [])}

{case_section}
## Policy references
{chr(10).join(policy_reference_lines)}

## Policy investigation agent trace
{chr(10).join(policy_search_lines)}

## Retrieval-augmented policy analysis
- Status: {policy_analysis.get("summary", "Not available")}
{chr(10).join(policy_analysis_lines)}
- This AI-assisted interpretation is for human review and does not make a legal determination.

## Outcome
- Workflow outcome: {state["workflow_outcome"]}
- Human decision: {human_decision}
- Reviewer: {state.get("reviewer", "Not recorded")}
- Decision rationale: {state.get("decision_rationale", "Not recorded")}

## Source Evidence
{chr(10).join(f'- {item["evidence_id"]} | {item["source_file"]} | locator={item.get("source_locator")} | {item["excerpt"]}' for item in state.get("evidence", []))}
"""

    return {"report": report}

builder = StateGraph(AMLState)
builder.add_node("validate_transaction", validate_transaction)
builder.add_node("compliance_check", compliance_check)
builder.add_node("assess_transaction_risk", assess_transaction_risk)
builder.add_node("transaction_specialist", transaction_specialist)
builder.add_node("customer_specialist", customer_specialist)
builder.add_node("policy_specialist", policy_specialist)
builder.add_node("policy_analysis_specialist", policy_analysis_specialist)
builder.add_node("policy_agent_decide", policy_agent_decide)
builder.add_node("policy_agent_search", policy_agent_search)
builder.add_node("synthesize_findings", synthesize_findings)
builder.add_node("review_case", review_case)
builder.add_node("report_generator", generate_report)
builder.add_node("create_alert_and_case", create_alert_and_case)


builder.add_edge(START, "validate_transaction")
builder.add_edge("validate_transaction", "compliance_check")
builder.add_edge("validate_transaction", "assess_transaction_risk")
builder.add_edge("validate_transaction", "transaction_specialist")
builder.add_edge("validate_transaction", "customer_specialist")
builder.add_edge("validate_transaction", "policy_specialist")
builder.add_edge("synthesize_findings", "policy_agent_decide")
builder.add_conditional_edges(
    "policy_agent_decide",
    route_policy_agent,
    {
        "search": "policy_agent_search",
        "finish": "policy_analysis_specialist",
    },
)
builder.add_edge("policy_agent_search", "policy_agent_decide")
builder.add_edge("policy_analysis_specialist", "create_alert_and_case")

builder.add_edge(
    [
        "compliance_check",
        "assess_transaction_risk",
        "transaction_specialist",
        "customer_specialist",
        "policy_specialist",
    ],
    "synthesize_findings",
)

builder.add_conditional_edges(
    "create_alert_and_case",
    route_after_analysis,
    {
        "review": "review_case",
        "clear": "report_generator",
    },
)

builder.add_edge("review_case", "report_generator")
builder.add_edge("report_generator", END)

graph = builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    input_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "samples"
        / "sample_transaction.txt"
    )
    source_text = input_path.read_text(encoding="utf-8")

    customer_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "samples"
        / "sample_customer.json"
    )
    raw_customer = json.loads(customer_path.read_text(encoding="utf-8"))

    model = ChatOllama(model="gemma4:e4b", temperature=0)
    extractor = model.with_structured_output(AMLTransaction)

    transaction = extractor.invoke(
    "Extract the transaction details from this text. Use only information "
    "supported by the text. If it gives only a date, use 00:00 UTC for the "
    "required timestamp.\n\n"
    f"{source_text}"
)

    raw_transaction = transaction.model_dump(mode="json")
    config = {"configurable": {"thread_id": "TX-1001"}}

    result = graph.invoke(
        {
            "raw_transaction": raw_transaction,
            "raw_customer": raw_customer,
            "source_file": input_path.name,
            "source_text": source_text,
        },
        config=config,
    )

    if result.get("__interrupt__"):
        while True:
            decision_value = input(
                "Case disposition ('close_no_action' or 'escalate'): "
            ).strip().casefold()

            if decision_value in {"close_no_action", "escalate"}:
                break

            print("Please enter 'close_no_action' or 'escalate'.")

        rationale = input("Reviewer rationale (at least 10 characters): ").strip()
        while len(rationale) < 10:
            rationale = input("Please enter a brief rationale: ").strip()

        decision = {
            "decision": decision_value,
            "rationale": rationale,
            "reviewer": "demo_reviewer",
        }
        result = graph.invoke(
            Command(resume=decision),
            config=config,
        )
    save_case(result)
    print("Saved case to:", "data/aml_cases.db")

    print(result["report"])
