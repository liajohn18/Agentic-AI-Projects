import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


DB_PATH = Path(__file__).resolve().parents[2] / "data" / "aml_cases.db"


def save_case(result: dict) -> None:
    transaction = result["transaction"]
    customer = result["customer"]
    case = result.get("case")
    alert = result.get("alert")

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transaction_reviews (
                transaction_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                transaction_data TEXT NOT NULL,
                customer_data TEXT NOT NULL,
                risk_assessment TEXT NOT NULL,
                compliance_flags TEXT NOT NULL,
                evidence_data TEXT NOT NULL DEFAULT '[]',
                policy_data TEXT NOT NULL DEFAULT '[]',
                workflow_outcome TEXT NOT NULL,
                human_decision TEXT,
                report TEXT NOT NULL
            )
            """
        )

        review_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(transaction_reviews)")
        }
        if "evidence_data" not in review_columns:
            connection.execute(
                "ALTER TABLE transaction_reviews "
                "ADD COLUMN evidence_data TEXT NOT NULL DEFAULT '[]'"
            )
        if "policy_data" not in review_columns:
            connection.execute(
                "ALTER TABLE transaction_reviews "
                "ADD COLUMN policy_data TEXT NOT NULL DEFAULT '[]'"
            )

        policy_data = {
            "references": result.get("policy_references", []),
            "analysis": result.get("policy_analysis", {}),
        }
        existing_policy_row = connection.execute(
            "SELECT policy_data FROM transaction_reviews WHERE transaction_id = ?",
            (transaction["transaction_id"],),
        ).fetchone()
        if existing_policy_row:
            try:
                existing_policy = json.loads(existing_policy_row[0] or "[]")
            except json.JSONDecodeError:
                existing_policy = None
            existing_analysis = (
                existing_policy.get("analysis", {})
                if isinstance(existing_policy, dict)
                else {}
            )
            if (
                existing_analysis.get("mode") == "search_only"
                and policy_data["analysis"].get("mode") != "search_only"
            ):
                # A background search may finish while a reviewer is recording a
                # decision. Preserve its result when the graph checkpoint is older.
                policy_data = existing_policy

        connection.execute(
            """
            INSERT OR REPLACE INTO transaction_reviews (
                transaction_id, customer_id, transaction_data, customer_data,
                risk_assessment, compliance_flags, evidence_data, policy_data,
                workflow_outcome, human_decision, report
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction["transaction_id"],
                customer["customer_id"],
                json.dumps(transaction),
                json.dumps(customer),
                json.dumps(result["risk_assessment"]),
                json.dumps(result["compliance_flags"]),
                json.dumps(result.get("evidence", [])),
                json.dumps(policy_data),
                result["workflow_outcome"],
                result.get("human_decision"),
                result.get("report", ""),
            ),
        )

        # Clear transactions have no case/alert record.
        if not case or not alert:
            investigations_table = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'investigations'"
            ).fetchone()
            if investigations_table:
                connection.execute(
                    "DELETE FROM investigations WHERE transaction_id = ?",
                    (transaction["transaction_id"],),
                )
            return

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS investigations (
                case_id TEXT PRIMARY KEY,
                transaction_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                alert_id TEXT NOT NULL,
                case_data TEXT NOT NULL,
                alert_data TEXT NOT NULL,
                transaction_data TEXT NOT NULL,
                customer_data TEXT NOT NULL,
                report TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO investigations (
                case_id, transaction_id, customer_id, alert_id,
                case_data, alert_data, transaction_data, customer_data, report
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case["case_id"],
                transaction["transaction_id"],
                customer["customer_id"],
                alert["alert_id"],
                json.dumps(case),
                json.dumps(alert),
                json.dumps(transaction),
                json.dumps(customer),
                result.get("report", ""),
            ),
        )


def save_policy_investigation(
    transaction_id: str,
    references: list[dict],
    analysis: dict,
    report: str | None = None,
) -> None:
    """Persist an on-demand policy agent run without rerunning the case graph."""
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            "SELECT policy_data FROM transaction_reviews WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"No saved transaction review for {transaction_id}.")

        try:
            saved_policy = json.loads(row[0] or "[]")
        except json.JSONDecodeError:
            saved_policy = []
        if isinstance(saved_policy, dict):
            saved_policy["references"] = references
            saved_policy["analysis"] = analysis
        else:
            saved_policy = {"references": references, "analysis": analysis}

        if report is None:
            connection.execute(
                "UPDATE transaction_reviews SET policy_data = ? "
                "WHERE transaction_id = ?",
                (json.dumps(saved_policy), transaction_id),
            )
        else:
            connection.execute(
                "UPDATE transaction_reviews SET policy_data = ?, report = ? "
                "WHERE transaction_id = ?",
                (json.dumps(saved_policy), report, transaction_id),
            )
            investigations_table = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'investigations'"
            ).fetchone()
            if investigations_table:
                connection.execute(
                    "UPDATE investigations SET report = ? WHERE transaction_id = ?",
                    (report, transaction_id),
                )


def load_policy_investigation(transaction_id: str) -> dict | None:
    """Load a previously saved on-demand policy investigation, if present."""
    with sqlite3.connect(DB_PATH) as connection:
        row = connection.execute(
            "SELECT policy_data FROM transaction_reviews WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
    if row is None:
        return None
    try:
        saved_policy = json.loads(row[0] or "[]")
    except json.JSONDecodeError:
        return None
    if isinstance(saved_policy, dict):
        analysis = saved_policy.get("analysis", {})
        if analysis.get("mode") == "search_only":
            return saved_policy
    return None


def record_case_event(
    transaction_id: str,
    case_id: str | None,
    event_type: str,
    actor: str,
    details: dict,
) -> None:
    """Append a case event. This is an application audit log, not tamper-proof storage."""
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS case_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT NOT NULL,
                case_id TEXT,
                occurred_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )
        # Reprocessing the same transaction can resume its existing case.
        # A case has one opening event, so don't append another copy.
        if event_type == "case_opened":
            existing_open = connection.execute(
                """
                SELECT 1 FROM case_events
                WHERE transaction_id = ? AND case_id IS ? AND event_type = ?
                LIMIT 1
                """,
                (transaction_id, case_id, event_type),
            ).fetchone()
            if existing_open:
                return
        connection.execute(
            """
            INSERT INTO case_events (
                transaction_id, case_id, occurred_at, event_type, actor, details
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                case_id,
                datetime.now(timezone.utc).isoformat(),
                event_type,
                actor,
                json.dumps(details, ensure_ascii=False),
            ),
        )


def load_case_events(transaction_id: str) -> list[dict]:
    """Return an investigation's append-only event history in time order."""
    if not DB_PATH.exists():
        return []
    with sqlite3.connect(DB_PATH) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='case_events'"
        ).fetchone()
        if table is None:
            return []
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT event_id, case_id, occurred_at, event_type, actor, details
            FROM case_events
            WHERE transaction_id = ?
            ORDER BY event_id
            """,
            (transaction_id,),
        ).fetchall()
    events = []
    case_opened_seen = False
    for row in rows:
        # Older versions logged another "case opened" every time a pending
        # transaction was reprocessed. Keep the first opening in the timeline.
        if row["event_type"] == "case_opened":
            if case_opened_seen:
                continue
            case_opened_seen = True
        try:
            details = json.loads(row["details"] or "{}")
        except json.JSONDecodeError:
            details = {}
        events.append({**dict(row), "details": details})
    return events
