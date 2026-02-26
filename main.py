#!/usr/bin/env python3
"""
BossBattle — AI Incident Response Agent for PixelCorp

Usage:
    python main.py                          # Run P2 auth incident (default)
    python main.py --incident INC-2026-0145 # Run specific incident by ID
    python main.py --all                    # Run all 4 incidents
"""

import json
import argparse
from pathlib import Path
from agent.graph import app
from agent.models import Incident, IncidentState
from agent.config import get_langgraph_config


def load_incidents() -> list[dict]:
    path = Path(__file__).parent / "seed" / "incidents.json"
    return json.loads(path.read_text())


def run_incident(incident_data: dict, thread_id: str) -> None:
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

    # Stream the graph execution
    for event in app.stream(initial_state, config=config, stream_mode="values"):
        pass  # State updates printed within each node

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


def main():
    parser = argparse.ArgumentParser(description="BossBattle Incident Response Agent")
    parser.add_argument("--incident", help="Incident ID to run (e.g. INC-2026-0142)")
    parser.add_argument("--all", action="store_true", help="Run all 4 incidents")
    args = parser.parse_args()

    incidents = load_incidents()

    if args.all:
        for i, inc in enumerate(incidents):
            run_incident(inc, thread_id=f"thread-{inc['id']}")
    elif args.incident:
        matches = [i for i in incidents if i["id"] == args.incident]
        if not matches:
            print(f"Incident {args.incident} not found in seed/incidents.json")
            return
        run_incident(matches[0], thread_id=f"thread-{matches[0]['id']}")
    else:
        # Default: run P2 auth incident (INC-2026-0142)
        run_incident(incidents[0], thread_id="thread-default")


if __name__ == "__main__":
    main()
