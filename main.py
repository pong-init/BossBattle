#!/usr/bin/env python3
"""
BossBattle — AI Incident Response Agent for PixelCorp

Usage:
    python main.py                          # Run P2 auth incident (default)
    python main.py --incident INC-2026-0145 # Run specific incident by ID
    python main.py --all                    # Run all 4 incidents
"""

import asyncio
import argparse
import json
import logging
from pathlib import Path

# Suppress noisy "Session termination failed: 202" from MCP client
logging.getLogger("mcp").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.WARNING)

from agent.config import (
    get_mcp_client,
    get_langgraph_config,
    get_model,
)
from agent.graph import build_graph
from agent.models import Incident, IncidentState
from observability.instrument import setup_observability


def load_incidents() -> list[dict]:
    path = Path(__file__).parent / "seed" / "incidents.json"
    return json.loads(path.read_text())


async def run_incident(
    incident_data: dict,
    app,
    thread_id: str,
) -> None:
    incident = Incident(**incident_data)
    initial_state = IncidentState(incident=incident)
    config = get_langgraph_config(thread_id)

    print(f"\n{'='*60}")
    print(f"BOSSBATTLE: Processing {incident.id}")
    print(f"  Title:    {incident.title}")
    print(f"  Service:  {incident.service}")
    print(f"  Metrics:  {incident.metrics.error_rate} error rate, "
          f"{incident.metrics.affected_users_estimate:,} users affected")
    print(f"{'='*60}")

    # Stream the graph — no interrupts expected with MCP Gateway auth
    async for chunk in app.astream(
        initial_state, config=config, stream_mode="updates"
    ):
        pass  # Nodes print their own progress

    # Print final state summary
    final_state = app.get_state(config)
    values = final_state.values
    print(f"\n{'='*60}")
    print(f"BOSSBATTLE COMPLETE: {incident.id}")
    print(f"  Severity:    {values.get('severity', 'unknown')}")
    print(f"  Linear:      {values.get('linear_ticket_url', 'not created')}")
    print(f"  Slack sent:  {values.get('slack_message_sent', False)}")
    print(f"  Email sent:  {values.get('email_sent', False)}")
    print(f"{'='*60}\n")


async def main():
    # Initialize OpenTelemetry instrumentation
    setup_observability()

    parser = argparse.ArgumentParser(description="BossBattle Incident Response Agent")
    parser.add_argument("--incident", help="Incident ID to run (e.g. INC-2026-0142)")
    parser.add_argument("--all", action="store_true", help="Run all 4 incidents")
    args = parser.parse_args()

    incidents = load_incidents()

    # Connect to Arcade MCP Gateway and load tools
    print("Connecting to Arcade MCP Gateway...")
    mcp_client = get_mcp_client()
    tools = await mcp_client.get_tools()
    print(f"Loaded {len(tools)} tools from MCP Gateway.")
    for t in tools[:5]:
        print(f"  Sample tool: {t.name}")
    if len(tools) > 5:
        print(f"  ... and {len(tools) - 5} more")

    model = get_model()
    app = build_graph(model=model, tools=tools)

    if args.all:
        for inc in incidents:
            await run_incident(inc, app, thread_id=f"thread-{inc['id']}")
    elif args.incident:
        matches = [i for i in incidents if i["id"] == args.incident]
        if not matches:
            print(f"Incident {args.incident} not found in seed/incidents.json")
            return
        await run_incident(matches[0], app, thread_id=f"thread-{matches[0]['id']}")
    else:
        # Default: first incident
        await run_incident(incidents[0], app, thread_id="thread-default")


if __name__ == "__main__":
    asyncio.run(main())
