import re
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from agent.models import IncidentState
from agent.prompts import SYSTEM_PROMPT, TICKET_PROMPT

PRIORITY_MAP = {
    "P1": "urgent",
    "P2": "high",
    "P3": "medium",
    "P4": "low",
}


def _extract_linear_url(result) -> str | None:
    """Extract Linear issue URL from tool result dict or string."""
    if isinstance(result, dict):
        issue = result.get("issue", {})
        identifier = issue.get("identifier")
        team = issue.get("team", {})
        team_key = team.get("key", "").lower() if team else ""
        if identifier and team_key:
            return f"https://linear.app/{team_key}/issue/{identifier}"
        # Fallback: search for URL in string representation
    match = re.search(r'https://linear\.app/\S+', str(result))
    return match.group(0).rstrip(".,)\"}'") if match else None


async def ticket_node(state: IncidentState, model_with_tools, tools_by_name: dict) -> dict:
    """Create a Linear ticket for the incident."""
    print(f"\n[TICKET] Creating Linear ticket for {state.incident.id} ({state.severity})")

    prompt = TICKET_PROMPT.format(
        severity=state.severity,
        incident_title=state.incident.title,
        description=state.incident.description,
        justification=state.severity_justification or "",
        error_rate=state.incident.metrics.error_rate,
        affected_users=state.incident.metrics.affected_users_estimate,
        github_summary=str(state.github_summary) if state.github_summary else "No recent commits identified as root cause.",
        incident_id=state.incident.id,
        started_at=state.incident.started_at,
        source=state.incident.source,
        priority=PRIORITY_MAP.get(state.severity, "medium"),
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    ticket_url = None

    while True:
        response = await model_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool = tools_by_name.get(tool_call["name"])
            if tool:
                print(f"[TICKET] Tool call: {tool_call['name']}")
                print(f"[TICKET] Args: {tool_call['args']}")
                try:
                    result = await tool.ainvoke(tool_call["args"])
                    print(f"[TICKET] Result: {str(result)[:500]}")
                    if tool_call["name"] == "Linear_CreateIssue" and ticket_url is None:
                        ticket_url = _extract_linear_url(result)
                except Exception as e:
                    result = f"Tool error: {e}"
                    print(f"[TICKET] Tool error: {e}")
                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    print(f"[TICKET] Created: {ticket_url or 'URL not found in response'}")

    return {
        "linear_ticket_url": ticket_url,
        "messages": messages,
    }
