from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from agent.models import IncidentState
from agent.prompts import SYSTEM_PROMPT, CONTEXT_PROMPT


async def context_node(state: IncidentState, model_with_tools, tools_by_name: dict) -> dict:
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

    # Agentic tool-calling loop — interrupt() fires inside each tool on auth
    while True:
        response = await model_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool = tools_by_name.get(tool_call["name"])
            if tool:
                print(f"[CONTEXT] Tool call: {tool_call['name']}")
                print(f"[CONTEXT] Args: {tool_call['args']}")
                try:
                    result = await tool.ainvoke(tool_call["args"])
                    print(f"[CONTEXT] Result: {str(result)[:500]}")
                except Exception as e:
                    result = f"Tool error: {e}"
                    print(f"[CONTEXT] Tool error: {e}")
                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    summary = str(response.content)
    print(f"[CONTEXT] GitHub summary: {summary[:200]}...")

    return {
        "github_summary": summary,
        "messages": messages,
    }
