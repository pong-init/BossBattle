from functools import partial
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from agent.models import IncidentState
from agent.nodes.triage import triage_node
from agent.nodes.context import context_node
from agent.nodes.ticket import ticket_node
from agent.nodes.notify import notify_node


def build_graph(
    model: ChatGoogleGenerativeAI,
    tools: list[BaseTool],
) -> any:
    """Build and compile the BossBattle StateGraph.

    Tools are loaded from the Arcade MCP Gateway. Each node gets only
    the tools it needs to prevent the model from going off-script.
    """
    tools_by_name = {t.name: t for t in tools}

    # Each node only gets the specific tools it needs
    github_tools = [t for t in tools if t.name.startswith(("Github_", "GithubApi_"))]
    linear_tools = [t for t in tools if t.name == "Linear_CreateIssue"]
    notify_tools = [t for t in tools if t.name in ("Slack_SendMessage", "Gmail_SendEmail")]

    workflow = StateGraph(IncidentState)

    workflow.add_node("triage", partial(triage_node, model=model))
    workflow.add_node("gather_context", partial(
        context_node,
        model_with_tools=model.bind_tools(github_tools),
        tools_by_name=tools_by_name,
    ))
    workflow.add_node("create_ticket", partial(
        ticket_node,
        model_with_tools=model.bind_tools(linear_tools),
        tools_by_name=tools_by_name,
    ))
    workflow.add_node("notify_team", partial(
        notify_node,
        model_with_tools=model.bind_tools(notify_tools),
        tools_by_name=tools_by_name,
    ))

    workflow.set_entry_point("triage")
    workflow.add_edge("triage", "gather_context")
    workflow.add_edge("gather_context", "create_ticket")
    workflow.add_edge("create_ticket", "notify_team")
    workflow.add_edge("notify_team", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
