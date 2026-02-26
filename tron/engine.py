"""Config-driven policy evaluation engine.

Reads policies.yaml and provides three evaluation functions:
  - evaluate_access(request) -> AccessHookResult
  - evaluate_pre(request)    -> PreHookResult
  - evaluate_post(request)   -> PostHookResult

All business logic lives in YAML. This module is pure plumbing.
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

from tron.models import (
    AccessHookRequest,
    AccessHookResult,
    AccessToolkitSpec,
    HookCode,
    PostHookOverride,
    PostHookRequest,
    PostHookResult,
    PreHookOverride,
    PreHookRequest,
    PreHookResult,
    ToolRequirement,
)


class PolicyEngine:
    """Loads and evaluates policies from a YAML config file."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).parent / "policies.yaml"
        self.config_path = Path(config_path)
        self.policies: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        """(Re)load policies from disk."""
        with open(self.config_path, encoding="utf-8") as f:
            self.policies = yaml.safe_load(f)

    # ── Access hook ─────────────────────────────────────────────

    def evaluate_access(self, request: AccessHookRequest) -> AccessHookResult:
        """Evaluate access rules. Returns deny dict for tools the user cannot see."""
        access_config = self.policies.get("access", {})
        deny_rules = access_config.get("deny_rules", [])
        deny_result: dict[str, AccessToolkitSpec] = {}

        for rule in deny_rules:
            if not self._user_matches_access_rule(request.user_id, rule):
                continue

            deny_spec = rule.get("deny", {})
            for toolkit_name, toolkit_conf in deny_spec.items():
                tool_names = toolkit_conf.get("tools", [])
                if toolkit_name not in deny_result:
                    deny_result[toolkit_name] = AccessToolkitSpec(tools={})
                for tool_name in tool_names:
                    if tool_name not in deny_result[toolkit_name].tools:
                        deny_result[toolkit_name].tools[tool_name] = [
                            ToolRequirement()
                        ]

        if deny_result:
            return AccessHookResult(deny=deny_result)
        return AccessHookResult()

    def _user_matches_access_rule(self, user_id: str, rule: dict) -> bool:
        """Check if a user_id matches an access rule's user filter."""
        if "user_id_not_in" in rule:
            return user_id not in rule["user_id_not_in"]

        if "user_id_matches" in rule:
            return bool(re.search(rule["user_id_matches"], user_id))

        if "user_id_in" in rule:
            return user_id in rule["user_id_in"]

        # No user filter — rule applies to everyone
        return True

    # ── Pre-execution hook ──────────────────────────────────────

    def evaluate_pre(self, request: PreHookRequest) -> PreHookResult:
        """Evaluate pre-execution rules. Returns block or override."""
        pre_config = self.policies.get("pre", {})
        rules = pre_config.get("rules", [])

        merged_overrides: dict[str, Any] = {}

        for rule in rules:
            if not self._tool_matches(rule.get("tool", "*"), request.tool.name):
                continue

            condition = rule.get("condition")
            if condition and not self._evaluate_condition(condition, request):
                continue

            action = rule.get("action", "block")

            if action == "block":
                return PreHookResult(
                    code=HookCode.CHECK_FAILED,
                    error_message=rule.get("error_message", "Blocked by policy"),
                )

            if action == "override":
                override_inputs = rule.get("override_inputs", {})
                merged_overrides.update(override_inputs)

        if merged_overrides:
            return PreHookResult(
                code=HookCode.OK,
                override=PreHookOverride(inputs=merged_overrides),
            )

        return PreHookResult(code=HookCode.OK)

    # ── Post-execution hook ─────────────────────────────────────

    def evaluate_post(self, request: PostHookRequest) -> PostHookResult:
        """Evaluate post-execution rules. Applies redactions to output."""
        post_config = self.policies.get("post", {})
        rules = post_config.get("rules", [])

        output = request.output
        any_redacted = False

        for rule in rules:
            if not self._tool_matches(rule.get("tool", "*"), request.tool.name):
                continue

            for redaction in rule.get("redactions", []):
                pattern = redaction.get("pattern", "")
                replacement = redaction.get("replacement", "[REDACTED]")
                if not pattern:
                    continue

                if isinstance(output, str):
                    new_output, count = re.subn(pattern, replacement, output)
                    if count > 0:
                        output = new_output
                        any_redacted = True
                elif isinstance(output, dict):
                    output, did_redact = self._redact_dict(
                        output, pattern, replacement
                    )
                    any_redacted = any_redacted or did_redact
                elif isinstance(output, list):
                    output, did_redact = self._redact_list(
                        output, pattern, replacement
                    )
                    any_redacted = any_redacted or did_redact

        if any_redacted:
            return PostHookResult(
                code=HookCode.OK,
                override=PostHookOverride(output=output),
            )

        return PostHookResult(code=HookCode.OK)

    # ── Helpers ─────────────────────────────────────────────────

    def _tool_matches(self, pattern: str, tool_name: str) -> bool:
        """Match tool name against pattern. Supports * wildcard and fnmatch."""
        if pattern == "*":
            return True
        return fnmatch(tool_name, pattern)

    def _evaluate_condition(self, condition: dict, request: PreHookRequest) -> bool:
        """Evaluate a single condition against the request."""
        field_path = condition.get("field", "")
        value = self._resolve_field(field_path, request)

        if value is None:
            # Field doesn't exist — "not_matches" should trigger, others shouldn't
            if "not_matches" in condition:
                return True
            if "not_equals" in condition:
                return True
            if "not_in" in condition:
                return True
            return False

        value_str = str(value)

        if "matches" in condition:
            return bool(re.search(condition["matches"], value_str))

        if "not_matches" in condition:
            return not bool(re.search(condition["not_matches"], value_str))

        if "equals" in condition:
            return value_str == str(condition["equals"])

        if "not_equals" in condition:
            return value_str != str(condition["not_equals"])

        if "in" in condition:
            return value_str in [str(v) for v in condition["in"]]

        if "not_in" in condition:
            return value_str not in [str(v) for v in condition["not_in"]]

        return False

    def _resolve_field(self, field_path: str, request: PreHookRequest) -> Any:
        """Resolve a dot-separated field path against the request.

        Supports: inputs.subject, tool.name, context.user_id, etc.
        """
        parts = field_path.split(".")
        obj: Any = request

        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return None

        return obj

    def _redact_dict(
        self, d: dict, pattern: str, replacement: str
    ) -> tuple[dict, bool]:
        """Recursively redact string values in a dict."""
        result = {}
        any_redacted = False
        for k, v in d.items():
            if isinstance(v, str):
                new_v, count = re.subn(pattern, replacement, v)
                if count > 0:
                    any_redacted = True
                result[k] = new_v
            elif isinstance(v, dict):
                result[k], did = self._redact_dict(v, pattern, replacement)
                any_redacted = any_redacted or did
            elif isinstance(v, list):
                result[k], did = self._redact_list(v, pattern, replacement)
                any_redacted = any_redacted or did
            else:
                result[k] = v
        return result, any_redacted

    def _redact_list(
        self, lst: list, pattern: str, replacement: str
    ) -> tuple[list, bool]:
        """Recursively redact string values in a list."""
        result = []
        any_redacted = False
        for item in lst:
            if isinstance(item, str):
                new_item, count = re.subn(pattern, replacement, item)
                if count > 0:
                    any_redacted = True
                result.append(new_item)
            elif isinstance(item, dict):
                new_item, did = self._redact_dict(item, pattern, replacement)
                any_redacted = any_redacted or did
                result.append(new_item)
            elif isinstance(item, list):
                new_item, did = self._redact_list(item, pattern, replacement)
                any_redacted = any_redacted or did
                result.append(new_item)
            else:
                result.append(item)
        return result, any_redacted
