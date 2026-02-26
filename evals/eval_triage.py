"""
BossBattle Triage Eval — Severity Classification (arcade_evals)

Tests that the model correctly classifies incident severity by calling
classify_severity with the right P1/P2/P3/P4 value.

Uses the arcade_evals framework with a provider-agnostic backend
for Google's OpenAI-compatible endpoint.
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from typing import Annotated
from openai import AsyncOpenAI

from arcade_tdk import ToolCatalog, tool
from arcade_evals import (
    EvalRubric,
    EvalSuite,
    ExpectedToolCall,
    tool_eval,
)
from arcade_evals.critic import BinaryCritic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from evals.backends import GeminiBackend, run_suite


# ── Mock tool: model must call this with the correct severity ──────────


@tool
def classify_severity(
    severity: Annotated[str, "The severity level — one of P1, P2, P3, P4."],
    justification: Annotated[str, "One sentence explaining which rule triggered."],
) -> str:
    """Classify an incident's severity level."""
    return f"Classified as {severity}"


# ── Register tools in Arcade catalog ───────────────────────────────────

catalog = ToolCatalog()
catalog.add_tool(classify_severity, "BossBattle")


# ── Rubric ─────────────────────────────────────────────────────────────

rubric = EvalRubric(
    fail_threshold=0.8,
    warn_threshold=0.95,
)

SYSTEM_MESSAGE = """You are BossBattle performing incident triage.

Classify the severity of the given incident using these rules:
- P1 (Critical): >50% error rate OR >10,000 users affected OR database/core infra down
- P2 (High): >10% error rate OR >1,000 users affected
- P3 (Medium): Performance degradation with <1,000 users affected
- P4 (Low): Cosmetic or minor issues, minimal user impact

You MUST call the classify_severity tool with your classification."""


# ── Eval suite ─────────────────────────────────────────────────────────


def bossbattle_triage_eval() -> EvalSuite:
    suite = EvalSuite(
        name="BossBattle Triage — Severity Classification",
        system_message=SYSTEM_MESSAGE,
        catalog=catalog,
        rubric=rubric,
    )

    # P1: 47% error rate, 12K users
    suite.add_case(
        name="Auth 500 errors → P1",
        user_message=json.dumps({
            "id": "INC-EVAL-001",
            "title": "Authentication service returning 500 errors",
            "description": "Multiple users reporting login failures. Auth service health check failing.",
            "metrics": {"error_rate": "47%", "affected_users_estimate": 12000},
        }),
        expected_tool_calls=[
            ExpectedToolCall(func=classify_severity, args={"severity": "P1"}),
        ],
        critics=[BinaryCritic(critic_field="severity", weight=1.0)],
    )

    # P3: 0.2% error rate, 500 users
    suite.add_case(
        name="Slow search → P3",
        user_message=json.dumps({
            "id": "INC-EVAL-002",
            "title": "Slow response times on product search",
            "description": "Search API p95 latency increased from 200ms to 1.2s. No errors, just slow.",
            "metrics": {"error_rate": "0.2%", "affected_users_estimate": 500},
        }),
        expected_tool_calls=[
            ExpectedToolCall(func=classify_severity, args={"severity": "P3"}),
        ],
        critics=[BinaryCritic(critic_field="severity", weight=1.0)],
    )

    # P4: 0% error rate, 50 users
    suite.add_case(
        name="CSS issue → P4",
        user_message=json.dumps({
            "id": "INC-EVAL-003",
            "title": "CSS rendering issue on checkout page",
            "description": "Button alignment broken on mobile checkout. Low impact.",
            "metrics": {"error_rate": "0%", "affected_users_estimate": 50},
        }),
        expected_tool_calls=[
            ExpectedToolCall(func=classify_severity, args={"severity": "P4"}),
        ],
        critics=[BinaryCritic(critic_field="severity", weight=1.0)],
    )

    # P1: 100% error rate, 85K users, database down
    suite.add_case(
        name="Database failover → P1",
        user_message=json.dumps({
            "id": "INC-EVAL-004",
            "title": "Database primary failover detected",
            "description": "PostgreSQL primary node unresponsive. All writes paused. CRITICAL.",
            "metrics": {"error_rate": "100%", "affected_users_estimate": 85000},
        }),
        expected_tool_calls=[
            ExpectedToolCall(func=classify_severity, args={"severity": "P1"}),
        ],
        critics=[BinaryCritic(critic_field="severity", weight=1.0)],
    )

    # P2: 15% error rate, 2K users
    suite.add_case(
        name="Payment errors → P2",
        user_message=json.dumps({
            "id": "INC-EVAL-005",
            "title": "Payment processing intermittent failures",
            "description": "15% of payment transactions failing with timeout.",
            "metrics": {"error_rate": "15%", "affected_users_estimate": 2000},
        }),
        expected_tool_calls=[
            ExpectedToolCall(func=classify_severity, args={"severity": "P2"}),
        ],
        critics=[BinaryCritic(critic_field="severity", weight=1.0)],
    )

    # Edge: Boundary — exactly 10% / 1K users
    suite.add_case(
        name="Boundary 10%/1K → P2",
        user_message=json.dumps({
            "id": "INC-EVAL-006",
            "title": "Notification service elevated error rate",
            "description": "Push notification delivery failing. Error rate steady at 10%.",
            "metrics": {"error_rate": "10%", "affected_users_estimate": 1000},
        }),
        expected_tool_calls=[
            ExpectedToolCall(func=classify_severity, args={"severity": "P2"}),
        ],
        critics=[BinaryCritic(critic_field="severity", weight=1.0)],
    )

    # Edge: Low metrics but infra keyword "down"
    suite.add_case(
        name="Infra down + low metrics → P1",
        user_message=json.dumps({
            "id": "INC-EVAL-007",
            "title": "Redis cluster primary node down",
            "description": "Redis primary node is down. Failover in progress. Cache reads falling back to database.",
            "metrics": {"error_rate": "2%", "affected_users_estimate": 300},
        }),
        expected_tool_calls=[
            ExpectedToolCall(func=classify_severity, args={"severity": "P1"}),
        ],
        critics=[BinaryCritic(critic_field="severity", weight=1.0)],
    )

    return suite


# ── Runner ─────────────────────────────────────────────────────────────


async def main():
    client = AsyncOpenAI(
        api_key=os.environ["GOOGLE_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    backend = GeminiBackend(client, model="gemini-2.5-flash-lite")

    suite = bossbattle_triage_eval()
    results = await run_suite(suite, backend)

    print("=" * 60)
    print("BOSSBATTLE TRIAGE EVAL (arcade_evals)")
    print("=" * 60)

    passed = 0
    for case in results["cases"]:
        status = "PASS" if case["evaluation"].passed else "FAIL"
        score = case["evaluation"].score
        if case["evaluation"].passed:
            passed += 1
        print(f"  [{status}] {case['name']} (score: {score:.2f})")
        if case["evaluation"].failure_reason:
            print(f"         Reason: {case['evaluation'].failure_reason}")

    total = len(results["cases"])
    print(f"\nResults: {passed}/{total} passed, {total - passed} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
