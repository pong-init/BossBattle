"""Unit tests for the Tron policy evaluation engine.

Tests the engine in isolation — no HTTP, no FastAPI, just pure policy logic.
"""

from pathlib import Path

import pytest

from tron.engine import PolicyEngine
from tron.models import (
    AccessHookRequest,
    HookCode,
    HookContext,
    PostHookRequest,
    PreHookRequest,
    ToolInfo,
)

POLICIES_PATH = Path(__file__).parent.parent / "policies.yaml"


@pytest.fixture
def engine():
    return PolicyEngine(config_path=POLICIES_PATH)


def _tool(name: str, toolkit: str = "Test") -> ToolInfo:
    return ToolInfo(name=name, toolkit=toolkit, version="1.0")


def _context(user_id: str = "alice@pixelcorp.com") -> HookContext:
    return HookContext(user_id=user_id)


# ── Pre-execution hook tests ───────────────────────────────────


class TestPreBlock:
    def test_block_email_for_p3_incident(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t1",
            tool=_tool("Gmail_SendEmail", "Gmail"),
            inputs={"subject": "[P3 INCIDENT] Slow search queries", "recipient": "vp-eng@pixelcorp.com"},
            context=_context(),
        ))
        assert result.code == HookCode.CHECK_FAILED
        assert "P3/P4" in result.error_message

    def test_block_email_for_p4_incident(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t2",
            tool=_tool("Gmail_SendEmail", "Gmail"),
            inputs={"subject": "[P4 INCIDENT] CSS rendering bug", "recipient": "vp-eng@pixelcorp.com"},
            context=_context(),
        ))
        assert result.code == HookCode.CHECK_FAILED

    def test_allow_email_for_p1_incident(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t3",
            tool=_tool("Gmail_SendEmail", "Gmail"),
            inputs={"subject": "[P1 INCIDENT] Database failover", "recipient": "vp-eng@pixelcorp.com"},
            context=_context(),
        ))
        assert result.code == HookCode.OK

    def test_allow_email_for_p2_incident(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t4",
            tool=_tool("Gmail_SendEmail", "Gmail"),
            inputs={"subject": "[P2 INCIDENT] Auth errors", "recipient": "vp-eng@pixelcorp.com"},
            context=_context(),
        ))
        assert result.code == HookCode.OK

    def test_block_slack_without_incident_id(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t5",
            tool=_tool("Slack_SendMessage", "Slack"),
            inputs={"channel_name": "#incidents", "message": "Something broke in production"},
            context=_context(),
        ))
        assert result.code == HookCode.CHECK_FAILED
        assert "incident id" in result.error_message.lower()

    def test_allow_slack_with_incident_id(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t6",
            tool=_tool("Slack_SendMessage", "Slack"),
            inputs={
                "channel_name": "#incidents",
                "message": "[P1] Auth down — INC-2026-0142 — 47% error rate",
            },
            context=_context(),
        ))
        assert result.code == HookCode.OK

    def test_block_email_to_unapproved_recipient(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t7",
            tool=_tool("Gmail_SendEmail", "Gmail"),
            inputs={"subject": "[P1 INCIDENT] DB down", "recipient": "random@gmail.com"},
            context=_context(),
        ))
        assert result.code == HookCode.CHECK_FAILED
        assert "approved" in result.error_message.lower()

    def test_allow_email_to_approved_recipient(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t8",
            tool=_tool("Gmail_SendEmail", "Gmail"),
            inputs={"subject": "[P1 INCIDENT] DB down", "recipient": "oncall@pixelcorp.com"},
            context=_context(),
        ))
        assert result.code == HookCode.OK

    def test_unrelated_tool_passes_through(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t9",
            tool=_tool("GithubApi_ListPullRequests", "Github"),
            inputs={"repo_owner": "pong-init", "repo_name": "pixelcorp-backend"},
            context=_context(),
        ))
        assert result.code == HookCode.OK


class TestPreOverride:
    def test_override_wrong_slack_channel(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t10",
            tool=_tool("Slack_SendMessage", "Slack"),
            inputs={
                "channel_name": "#general",
                "message": "Incident INC-2026-0142 is active",
            },
            context=_context(),
        ))
        assert result.code == HookCode.OK
        assert result.override is not None
        assert result.override.inputs["channel_name"] == "#incidents"

    def test_no_override_for_correct_channel(self, engine):
        result = engine.evaluate_pre(PreHookRequest(
            execution_id="t11",
            tool=_tool("Slack_SendMessage", "Slack"),
            inputs={
                "channel_name": "#incidents",
                "message": "Incident INC-2026-0142 is active",
            },
            context=_context(),
        ))
        assert result.code == HookCode.OK
        assert result.override is None


# ── Post-execution hook tests ──────────────────────────────────


class TestPostRedaction:
    def test_redact_email_addresses(self, engine):
        result = engine.evaluate_post(PostHookRequest(
            execution_id="t20",
            tool=_tool("GithubApi_ListPullRequests", "Github"),
            output="PR by john@example.com merged yesterday",
            context=_context(),
        ))
        assert result.code == HookCode.OK
        assert result.override is not None
        assert "[EMAIL_REDACTED]" in result.override.output
        assert "john@example.com" not in result.override.output

    def test_redact_ip_addresses(self, engine):
        result = engine.evaluate_post(PostHookRequest(
            execution_id="t21",
            tool=_tool("Slack_SendMessage", "Slack"),
            output="Server at 10.0.1.42 is unreachable",
            context=_context(),
        ))
        assert result.override is not None
        assert "[IP_REDACTED]" in result.override.output
        assert "10.0.1.42" not in result.override.output

    def test_redact_github_tokens(self, engine):
        token = "ghp_" + "A" * 36
        result = engine.evaluate_post(PostHookRequest(
            execution_id="t22",
            tool=_tool("GithubApi_ListPullRequests", "Github"),
            output=f"Found token {token} in config",
            context=_context(),
        ))
        assert result.override is not None
        assert "[GITHUB_TOKEN_REDACTED]" in result.override.output
        assert token not in result.override.output

    def test_clean_output_passes_through(self, engine):
        result = engine.evaluate_post(PostHookRequest(
            execution_id="t23",
            tool=_tool("Linear_CreateIssue", "Linear"),
            output="Ticket PIX-42 created successfully",
            context=_context(),
        ))
        assert result.code == HookCode.OK
        assert result.override is None

    def test_redact_nested_dict_output(self, engine):
        result = engine.evaluate_post(PostHookRequest(
            execution_id="t24",
            tool=_tool("GithubApi_ListPullRequests", "Github"),
            output={
                "title": "Fix auth",
                "author": "john@corp.com",
                "metadata": {"reviewer": "jane@corp.com", "ip": "192.168.1.1"},
            },
            context=_context(),
        ))
        assert result.override is not None
        out = result.override.output
        assert out["author"] == "[EMAIL_REDACTED]"
        assert out["metadata"]["reviewer"] == "[EMAIL_REDACTED]"
        assert out["metadata"]["ip"] == "[IP_REDACTED]"

    def test_redact_list_output(self, engine):
        result = engine.evaluate_post(PostHookRequest(
            execution_id="t25",
            tool=_tool("GithubApi_ListPullRequests", "Github"),
            output=["PR by alice@corp.com", "PR by bob@corp.com"],
            context=_context(),
        ))
        assert result.override is not None
        assert all("[EMAIL_REDACTED]" in item for item in result.override.output)

    def test_multiple_redactions_in_one_string(self, engine):
        result = engine.evaluate_post(PostHookRequest(
            execution_id="t26",
            tool=_tool("GithubApi_ListPullRequests", "Github"),
            output="Contact john@corp.com at 10.0.0.1 for details",
            context=_context(),
        ))
        assert result.override is not None
        assert "[EMAIL_REDACTED]" in result.override.output
        assert "[IP_REDACTED]" in result.override.output


# ── Access hook tests ──────────────────────────────────────────


class TestAccess:
    def test_deny_gmail_for_non_commander(self, engine):
        result = engine.evaluate_access(AccessHookRequest(
            user_id="random@pixelcorp.com",
            toolkits={},
        ))
        assert result.deny is not None
        assert "Gmail" in result.deny
        assert "Gmail_SendEmail" in result.deny["Gmail"].tools

    def test_allow_gmail_for_commander(self, engine):
        result = engine.evaluate_access(AccessHookRequest(
            user_id="alice@pixelcorp.com",
            toolkits={},
        ))
        # Alice is in the allow list, so Gmail should not be denied
        if result.deny:
            assert "Gmail" not in result.deny

    def test_deny_linear_for_intern(self, engine):
        result = engine.evaluate_access(AccessHookRequest(
            user_id="jane.intern@pixelcorp.com",
            toolkits={},
        ))
        assert result.deny is not None
        assert "Linear" in result.deny
        assert "Linear_CreateIssue" in result.deny["Linear"].tools

    def test_allow_linear_for_regular_user(self, engine):
        result = engine.evaluate_access(AccessHookRequest(
            user_id="dev@pixelcorp.com",
            toolkits={},
        ))
        # Regular user is not an intern — Linear should not be denied
        if result.deny and "Linear" in result.deny:
            pytest.fail("Regular user should not be denied Linear access")

    def test_intern_denied_both_gmail_and_linear(self, engine):
        result = engine.evaluate_access(AccessHookRequest(
            user_id="new.intern@pixelcorp.com",
            toolkits={},
        ))
        assert result.deny is not None
        assert "Gmail" in result.deny
        assert "Linear" in result.deny


# ── Policies YAML validation ──────────────────────────────────


class TestPoliciesYaml:
    def test_yaml_parses(self, engine):
        assert engine.policies is not None
        assert "pre" in engine.policies
        assert "post" in engine.policies
        assert "access" in engine.policies

    def test_all_rules_have_descriptions(self, engine):
        for section in ("pre", "post", "access"):
            config = engine.policies.get(section, {})
            rules = config.get("rules", config.get("deny_rules", []))
            for rule in rules:
                assert "description" in rule, f"Rule missing description in {section}: {rule}"

    def test_all_regex_patterns_compile(self, engine):
        import re

        for rule in engine.policies.get("pre", {}).get("rules", []):
            cond = rule.get("condition", {})
            for key in ("matches", "not_matches"):
                if key in cond:
                    re.compile(cond[key])  # Raises on invalid regex

        for rule in engine.policies.get("post", {}).get("rules", []):
            for redaction in rule.get("redactions", []):
                if "pattern" in redaction:
                    re.compile(redaction["pattern"])

        for rule in engine.policies.get("access", {}).get("deny_rules", []):
            if "user_id_matches" in rule:
                re.compile(rule["user_id_matches"])
