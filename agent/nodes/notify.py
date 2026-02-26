from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from agent.models import IncidentState
from agent.prompts import SYSTEM_PROMPT, NOTIFY_PROMPT
from agent.config import VP_ENG_EMAIL


async def notify_node(state: IncidentState, model_with_tools, tools_by_name: dict) -> dict:
    """Post to Slack #incidents. For P1/P2, also email VP Eng."""
    print(f"\n[NOTIFY] Sending notifications for {state.severity} incident")

    send_email = state.severity in ("P1", "P2")

    if send_email:
        email_instruction = (
            f"Also send an email to {VP_ENG_EMAIL} with subject "
            f"'[{state.severity} INCIDENT] {state.incident.title}' and a brief summary."
        )
    else:
        email_instruction = "Do NOT send an email (P3/P4 severity — Slack only)."

    prompt = NOTIFY_PROMPT.format(
        severity=state.severity,
        incident_title=state.incident.title,
        ticket_url=state.linear_ticket_url or "No ticket URL",
        description=state.incident.description,
        error_rate=state.incident.metrics.error_rate,
        affected_users=state.incident.metrics.affected_users_estimate,
        email_instruction=email_instruction,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    slack_sent = False
    email_actually_sent = False

    while True:
        response = await model_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool = tools_by_name.get(tool_call["name"])
            if tool:
                print(f"[NOTIFY] Tool call: {tool_call['name']}")
                print(f"[NOTIFY] Args: {tool_call['args']}")
                try:
                    result = await tool.ainvoke(tool_call["args"])
                    print(f"[NOTIFY] Result: {str(result)[:500]}")
                    if tool_call["name"] == "Slack_SendMessage":
                        slack_sent = True
                    if tool_call["name"] == "Gmail_SendEmail":
                        email_actually_sent = True
                except Exception as e:
                    result = f"Tool error: {e}"
                    print(f"[NOTIFY] Tool error: {e}")
                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    print(f"[NOTIFY] Done. Slack sent: {slack_sent}, Email sent: {email_actually_sent}")

    return {
        "slack_message_sent": slack_sent,
        "email_sent": email_actually_sent,
        "notifications_summary": str(response.content),
        "messages": messages,
    }
