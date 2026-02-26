from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from agent.models import IncidentState
from agent.nodes import triage_node, context_node, ticket_node, notify_node

workflow = StateGraph(IncidentState)

workflow.add_node("triage", triage_node)
workflow.add_node("gather_context", context_node)
workflow.add_node("create_ticket", ticket_node)
workflow.add_node("notify_team", notify_node)

workflow.set_entry_point("triage")
workflow.add_edge("triage", "gather_context")
workflow.add_edge("gather_context", "create_ticket")
workflow.add_edge("create_ticket", "notify_team")
workflow.add_edge("notify_team", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
