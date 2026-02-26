from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from agent.models import IncidentState
from agent.prompts import SYSTEM_PROMPT, TICKET_PROMPT
from agent.config import model_with_tools, tools


_tool_node = ToolNode(tools)

PRIORITY_MAP = {
    "P1": "urgent",
    "P2": "high",
    "P3": "medium",
    "P4": "low",
}


def ticket_node(state: IncidentState) -> dict:
    """Create a Linear ticket for the incident."""
    print(f"\n[TICKET] Creating Linear ticket for {state.incident.id} ({state.severity})")

    prompt = TICKET_PROMPT.format(
        severity=state.severity,
        incident_title=state.incident.title,
        description=state.incident.description,
        justification=state.severity_justification or "",
        error_rate=state.incident.metrics.error_rate,
        affected_users=state.incident.metrics.affected_users_estimate,
        github_summary=state.github_summary or "No recent commits identified as root cause.",
        incident_id=state.incident.id,
        started_at=state.incident.started_at,
        source=state.incident.source,
        priority=PRIORITY_MAP.get(state.severity, "medium"),
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    while True:
        response = model_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        tool_results = _tool_node.invoke({"messages": messages})
        messages.extend(tool_results["messages"])

    # Extract ticket URL from response
    content = response.content
    ticket_url = None
    for word in content.split():
        if "linear.app" in word:
            ticket_url = word.strip(".,")
            break

    print(f"[TICKET] Created: {ticket_url or 'URL not found in response'}")

    return {
        "linear_ticket_url": ticket_url,
        "messages": messages,
    }
