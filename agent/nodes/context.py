from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from agent.models import IncidentState
from agent.prompts import SYSTEM_PROMPT, CONTEXT_PROMPT
from agent.config import model_with_tools, tools


_tool_node = ToolNode(tools)


def context_node(state: IncidentState) -> dict:
    """Search GitHub for recent commits related to the incident."""
    print(f"\n[CONTEXT] Gathering GitHub context for service: {state.incident.service}")

    prompt = CONTEXT_PROMPT.format(
        service=state.incident.service,
        description=state.incident.description,
    )

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    # Agentic loop: keep calling tools until the model stops
    while True:
        response = model_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        # Execute tool calls (may trigger LangGraph interrupt for OAuth)
        tool_results = _tool_node.invoke({"messages": messages})
        messages.extend(tool_results["messages"])

    summary = response.content
    print(f"[CONTEXT] GitHub summary: {summary[:200]}...")

    return {
        "github_summary": summary,
        "messages": messages,
    }
