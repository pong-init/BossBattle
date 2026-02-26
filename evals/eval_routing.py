"""
BossBattle Routing Eval — Notification Logic (arcade_evals)

Tests that the model correctly routes notifications:
  - ALL severities: Slack_SendMessage to #incidents
  - P1/P2 ONLY: Also Gmail_SendEmail to VP of Engineering
  - P3/P4: Slack only, no email

Uses the arcade_evals framework with a provider-agnostic backend
for Google's OpenAI-compatible endpoint.
"""

import asyncio
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
from arcade_evals.critic import BinaryCritic, SimilarityCritic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from evals.backends import GeminiBackend, run_suite

VP_ENG_EMAIL = os.environ.get("VP_ENG_EMAIL", "pixelcorp.demo@gmail.com")


# ── Mock tools: same schema as MCP Gateway tools ──────────────────────


@tool
def Slack_SendMessage(
    channel_name: Annotated[str, "The Slack channel to post to (e.g. #incidents)."],
    message: Annotated[str, "The message content to send."],
) -> str:
    """Send a message to a Slack channel."""
    return '{"ok": true}'


@tool
def Gmail_SendEmail(
    recipient: Annotated[str, "The email address to send to."],
    subject: Annotated[str, "The email subject line."],
    body: Annotated[str, "The email body content."],
) -> str:
    """Send an email via Gmail."""
    return '{"ok": true}'


# ── Register tools in Arcade catalog ───────────────────────────────────

catalog = ToolCatalog()
catalog.add_tool(Slack_SendMessage, "BossBattle")
catalog.add_tool(Gmail_SendEmail, "BossBattle")


# ── Rubric ─────────────────────────────────────────────────────────────

rubric = EvalRubric(
    fail_threshold=0.8,
    warn_threshold=0.95,
    fail_on_tool_selection=True,
    fail_on_tool_call_quantity=True,
)

SYSTEM_MESSAGE = """You are BossBattle sending incident notifications.

You MUST perform these actions in order:
1. ALWAYS call Slack_SendMessage with channel_name "#incidents" and a message
   containing the severity, title, metrics, and Linear ticket link.
2. For P1/P2 incidents ONLY: Also call Gmail_SendEmail to notify the VP of Engineering.
3. For P3/P4 incidents: Do NOT call Gmail_SendEmail. Slack only.

Do NOT skip any required action. Call the tools now."""


# ── Eval suite ─────────────────────────────────────────────────────────


def bossbattle_routing_eval() -> EvalSuite:
    suite = EvalSuite(
        name="BossBattle Routing — Notification Logic",
        system_message=SYSTEM_MESSAGE,
        catalog=catalog,
        rubric=rubric,
    )

    # P1 → Slack + Email
    suite.add_case(
        name="P1 → Slack + Email",
        user_message=(
            "[P1] Database primary failover detected. "
            "100% error rate, 85000 users affected. "
            f"Ticket: https://linear.app/pixelcorp/issue/PIX-1. "
            f"Email VP at {VP_ENG_EMAIL}."
        ),
        expected_tool_calls=[
            ExpectedToolCall(
                func=Slack_SendMessage,
                args={"channel_name": "#incidents"},
            ),
            ExpectedToolCall(
                func=Gmail_SendEmail,
                args={"recipient": VP_ENG_EMAIL},
            ),
        ],
        critics=[
            BinaryCritic(critic_field="channel_name", weight=0.5),
            BinaryCritic(critic_field="recipient", weight=0.5),
        ],
    )

    # P2 → Slack + Email
    suite.add_case(
        name="P2 → Slack + Email",
        user_message=(
            "[P2] Payment processing intermittent failures. "
            "15% error rate, 2000 users affected. "
            f"Ticket: https://linear.app/pixelcorp/issue/PIX-2. "
            f"Email VP at {VP_ENG_EMAIL}."
        ),
        expected_tool_calls=[
            ExpectedToolCall(
                func=Slack_SendMessage,
                args={"channel_name": "#incidents"},
            ),
            ExpectedToolCall(
                func=Gmail_SendEmail,
                args={"recipient": VP_ENG_EMAIL},
            ),
        ],
        critics=[
            BinaryCritic(critic_field="channel_name", weight=0.5),
            BinaryCritic(critic_field="recipient", weight=0.5),
        ],
    )

    # P3 → Slack only (no email)
    suite.add_case(
        name="P3 → Slack only",
        user_message=(
            "[P3] Slow response times on product search. "
            "0.2% error rate, 500 users affected. "
            "Ticket: https://linear.app/pixelcorp/issue/PIX-3. "
            "Do NOT send email (P3 severity — Slack only)."
        ),
        expected_tool_calls=[
            ExpectedToolCall(
                func=Slack_SendMessage,
                args={"channel_name": "#incidents"},
            ),
        ],
        critics=[
            BinaryCritic(critic_field="channel_name", weight=1.0),
        ],
    )

    # P4 → Slack only (no email)
    suite.add_case(
        name="P4 → Slack only",
        user_message=(
            "[P4] CSS rendering issue on checkout page. "
            "0% error rate, 50 users affected. "
            "Ticket: https://linear.app/pixelcorp/issue/PIX-4. "
            "Do NOT send email (P4 severity — Slack only)."
        ),
        expected_tool_calls=[
            ExpectedToolCall(
                func=Slack_SendMessage,
                args={"channel_name": "#incidents"},
            ),
        ],
        critics=[
            BinaryCritic(critic_field="channel_name", weight=1.0),
        ],
    )

    return suite


# ── Runner ─────────────────────────────────────────────────────────────


async def main():
    client = AsyncOpenAI(
        api_key=os.environ["GOOGLE_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    backend = GeminiBackend(client, model="gemini-2.5-flash-lite")

    suite = bossbattle_routing_eval()
    results = await run_suite(suite, backend)

    print("=" * 60)
    print("BOSSBATTLE ROUTING EVAL (arcade_evals)")
    print("=" * 60)

    passed = 0
    for case in results["cases"]:
        status = "PASS" if case["evaluation"].passed else "FAIL"
        score = case["evaluation"].score
        if case["evaluation"].passed:
            passed += 1

        actual_tools = [tc.get("name", "?") for tc in case.get("predicted_tool_calls", [])]
        print(f"  [{status}] {case['name']}: tools={actual_tools} (score: {score:.2f})")
        if case["evaluation"].failure_reason:
            print(f"         Reason: {case['evaluation'].failure_reason}")

    total = len(results["cases"])
    print(f"\nResults: {passed}/{total} passed, {total - passed} failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
