from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from agent.models import IncidentState
from agent.prompts import SYSTEM_PROMPT, NOTIFY_PROMPT
from agent.config import model_with_tools, tools, VP_ENG_EMAIL


_tool_node = ToolNode(tools)


def notify_node(state: IncidentState) -> dict:
    """Post to Slack #incidents. For P1/P2, also email VP Eng."""
    print(f"\n[NOTIFY] Sending notifications for {state.severity} incident")

    send_email = state.severity in ("P1", "P2")

    prompt = NOTIFY_PROMPT.format(
        severity=state.severity,
        incident_title=state.incident.title,
        ticket_url=state.linear_ticket_url or "No ticket URL",
        description=state.incident.description,
        error_rate=state.incident.metrics.error_rate,
        affected_users=state.incident.metrics.affected_users_estimate,
        vp_email=VP_ENG_EMAIL,
        send_email=send_email,
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

    print(f"[NOTIFY] Done. Email sent: {send_email}")
    print(f"[NOTIFY] Response: {response.content[:200]}...")

    return {
        "slack_message_sent": True,
        "email_sent": send_email,
        "notifications_summary": response.content,
        "messages": messages,
    }
