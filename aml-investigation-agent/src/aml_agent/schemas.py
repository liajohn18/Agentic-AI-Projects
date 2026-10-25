from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Literal


class AMLTransaction(BaseModel):
    transaction_id: str
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    timestamp: datetime
    sender_name: str
    beneficiary_name: str
    channel: Literal["wire", "cash", "card"]
    description: str
    account_id: str | None = None
    direction: Literal["inbound", "outbound"] | None = None

class RiskAssessment(BaseModel):
    risk_score: float = Field(ge=0, le=1)
    risk_level: Literal["low", "medium", "high"]
    indicators: list[str]
    rationale: str

class Customer(BaseModel):
    customer_id: str
    legal_name: str
    country_code: str = Field(min_length=2, max_length=2)
    risk_rating: Literal["low", "medium", "high"]
    customer_type: str | None = None
    industry: str | None = None
    kyc_status: str | None = None
    expected_monthly_turnover_usd: Decimal | None = Field(default=None, ge=0)
    source_of_funds: str | None = None
    kyc_last_reviewed: str | None = None
    pep_status: str | None = None
    sanctions_screening_status: str | None = None


class EvidenceRecord(BaseModel):
    evidence_id: str
    source_file: str
    source_type: Literal["csv", "pdf", "text", "policy", "system"]
    source_locator: str | None = None
    field_name: str | None = None
    excerpt: str
    confidence: float | None = Field(default=None, ge=0, le=1)


class PolicyRagFinding(BaseModel):
    policy_id: str
    observation: str
    supporting_quote: str


class PolicyRagAnalysis(BaseModel):
    summary: str
    findings: list[PolicyRagFinding]
    open_questions: list[str] = Field(default_factory=list)


class PolicySearchDecision(BaseModel):
    """A bounded, auditable choice made by the policy investigation agent."""

    action: Literal["search_policy", "finish"]
    query: str = Field(default="", max_length=240)
    rationale: str = Field(default="", max_length=300)


class AMLAlert(BaseModel):
    alert_id: str
    customer_id: str
    transaction_ids: list[str] = Field(min_length=1)
    alert_type: str
    created_at: datetime
    status: Literal["open", "in_review", "closed"] = "open"


class AMLCase(BaseModel):
    case_id: str
    customer_id: str
    alert_ids: list[str] = Field(min_length=1)
    status: Literal["open", "in_review", "escalated", "closed"] = "open"
    assigned_to: str | None = None
    decision: Literal["close_no_action", "escalate"] | None = None
    decision_rationale: str | None = None
    reviewer: str | None = None
    opened_at: datetime
    closed_at: datetime | None = None
