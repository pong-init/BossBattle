import json
from langchain_core.messages import HumanMessage
from agent.models import IncidentState
from agent.prompts import TRIAGE_PROMPT


async def triage_node(state: IncidentState, model) -> dict:
    """Classify incident severity using LLM reasoning. No tools needed."""
    print(f"\n[TRIAGE] Processing incident: {state.incident.id}")

    prompt = TRIAGE_PROMPT.format(
        incident_json=json.dumps(state.incident.model_dump(), indent=2)
    )

    response = await model.ainvoke([HumanMessage(content=prompt)])
    content = str(response.content)

    severity = None
    for level in ["P1", "P2", "P3", "P4"]:
        if level in content:
            severity = level
            break

    if not severity:
        severity = "P2"  # safe default

    print(f"[TRIAGE] Classified as {severity}")

    return {
        "severity": severity,
        "severity_justification": content,
    }
