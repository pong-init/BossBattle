from typing import Any, Optional, Annotated
from pydantic import BaseModel
from langgraph.graph.message import add_messages


class IncidentMetrics(BaseModel):
    error_rate: str
    affected_users_estimate: int
    p99_latency_ms: Optional[int] = None
    p95_latency_ms: Optional[int] = None


class Incident(BaseModel):
    id: str
    title: str
    description: str
    severity_hint: str
    service: str
    environment: str
    started_at: str
    source: str
    metrics: IncidentMetrics


class IncidentState(BaseModel):
    # Input
    incident: Incident

    # Triage output
    severity: Optional[str] = None          # P1, P2, P3, P4
    severity_justification: Optional[Any] = None

    # Context output
    relevant_commits: Optional[list[dict]] = None
    github_summary: Optional[Any] = None

    # Ticket output
    linear_ticket_url: Optional[str] = None
    linear_ticket_id: Optional[str] = None

    # Notify output
    slack_message_sent: bool = False
    email_sent: bool = False
    notifications_summary: Optional[Any] = None

    # LangGraph messages (for tool calls within nodes)
    messages: Annotated[list, add_messages] = []
