"""
Provider-agnostic inference backends for arcade_evals.

arcade_evals' EvalSuite.run() assumes Arcade's hosted engine, which resolves
tool schemas server-side. This module provides an InferenceBackend protocol
and implementations for running evals against any LLM provider.

Usage:
    from evals.backends import GeminiBackend, run_suite

    backend = GeminiBackend(client, model="gemini-2.5-flash-lite")
    results = await run_suite(suite, backend)

Backends:
    ArcadeEngineBackend  — Arcade's hosted engine (string tool names, seed)
    OpenAIBackend        — OpenAI API directly (full schemas, seed)
    GeminiBackend        — Google's OpenAI-compatible endpoint (no seed/strict)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from arcade_core.converters.openai import to_openai
from arcade_evals.eval import EvalSuite, normalize_name


# ── Data types ─────────────────────────────────────────────────────────


@dataclass
class ToolCallResult:
    """A tool call parsed from an LLM response."""

    name: str  # Must be compatible with catalog.get_tool_by_name()
    args: dict[str, Any]


# ── Protocol ───────────────────────────────────────────────────────────


@runtime_checkable
class InferenceBackend(Protocol):
    """Interface for LLM inference providers used in evals.

    Each backend handles provider-specific concerns:
    - Tool schema format (name strings vs full function schemas)
    - Supported API parameters (seed, strict, user, etc.)
    - Tool name mapping between LLM response and catalog lookup

    Returned ToolCallResult.name values must work with both
    catalog.get_tool_by_name() and compare_tool_name() in evaluation.
    """

    @property
    def model_name(self) -> str: ...

    async def call_with_tools(
        self,
        messages: list[dict[str, str]],
        tool_names: list,
        catalog: Any,
    ) -> list[ToolCallResult]: ...


# ── Shared helpers ─────────────────────────────────────────────────────


def _parse_tool_calls(response) -> list[tuple[str, dict[str, Any]]]:
    """Extract (name, args) tuples from an OpenAI-format chat completion."""
    results = []
    message = response.choices[0].message
    if message.tool_calls:
        for tc in message.tool_calls:
            results.append((tc.function.name, json.loads(tc.function.arguments)))
    return results


def _build_openai_schemas(tool_names, catalog):
    """Convert catalog tools to OpenAI tool schemas with a name reverse-map.

    Returns:
        (schemas, name_map) where name_map maps the LLM-facing normalized
        name (underscores) back to the catalog FQN string (dots).
    """
    schemas = []
    name_map = {}
    for fqn in tool_names:
        tool = catalog[fqn]
        schema = to_openai(tool)
        llm_name = schema["function"]["name"]  # normalized: BossBattle_Tool
        catalog_name = str(fqn)  # original FQN: BossBattle.Tool
        name_map[llm_name] = catalog_name
        schemas.append(schema)
    return schemas, name_map


def _resolve_names(raw_calls, name_map):
    """Map LLM-facing tool names back to catalog-compatible FQN strings."""
    return [
        ToolCallResult(name=name_map.get(name, name), args=args)
        for name, args in raw_calls
    ]


# ── Backend implementations ────────────────────────────────────────────


class ArcadeEngineBackend:
    """Arcade's hosted engine — passes tool name strings, supports seed.

    Use when evaluating against Arcade's inference proxy at api.arcade.dev.
    The engine resolves tool schemas server-side from registered tool names.
    """

    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def call_with_tools(self, messages, tool_names, catalog):
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tool_choice="auto",
            tools=(str(name) for name in tool_names),
            user="eval_user",
            seed=42,
            stream=False,
        )
        raw = _parse_tool_calls(response)
        return [
            ToolCallResult(name=normalize_name(name), args=args)
            for name, args in raw
        ]


class OpenAIBackend:
    """OpenAI API directly — full tool schemas, supports seed.

    Use when evaluating against OpenAI's API (api.openai.com).
    Sends complete function schemas so OpenAI can validate tool calls.
    """

    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def call_with_tools(self, messages, tool_names, catalog):
        schemas, name_map = _build_openai_schemas(tool_names, catalog)

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tool_choice="auto",
            tools=schemas,
            seed=42,
            stream=False,
        )
        return _resolve_names(_parse_tool_calls(response), name_map)


class GeminiBackend:
    """Google's OpenAI-compatible endpoint — no seed, no strict mode.

    Use when evaluating against generativelanguage.googleapis.com.
    Strips parameters that Gemini's endpoint doesn't support.
    """

    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    async def call_with_tools(self, messages, tool_names, catalog):
        schemas, name_map = _build_openai_schemas(tool_names, catalog)

        for schema in schemas:
            schema["function"].pop("strict", None)
            params = schema.get("function", {}).get("parameters", {})
            params.pop("additionalProperties", None)

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tool_choice="auto",
            tools=schemas,
            stream=False,
        )
        return _resolve_names(_parse_tool_calls(response), name_map)


# ── Provider-agnostic runner ───────────────────────────────────────────


async def run_suite(suite: EvalSuite, backend: InferenceBackend) -> dict[str, Any]:
    """Run an EvalSuite against any inference backend.

    Drop-in alternative to suite.run(client, model) that works with any
    provider, not just Arcade's engine.

    Args:
        suite: The configured EvalSuite with cases and catalog.
        backend: An InferenceBackend implementation for the target provider.

    Returns:
        Results dict matching the shape of EvalSuite.run() output.
    """
    results: dict[str, Any] = {
        "model": backend.model_name,
        "rubric": suite.rubric,
        "cases": [],
    }

    semaphore = asyncio.Semaphore(suite.max_concurrent)
    tool_names = list(suite.catalog.get_tool_names())

    async def sem_task(case) -> dict[str, Any]:
        async with semaphore:
            messages = [{"role": "system", "content": case.system_message}]
            messages.extend(case.additional_messages)
            messages.append({"role": "user", "content": case.user_message})

            tool_calls = await backend.call_with_tools(
                messages, tool_names, suite.catalog
            )

            filled = []
            for tc in tool_calls:
                tool = suite.catalog.get_tool_by_name(tc.name)
                if tool is None:
                    raise ValueError(f"Tool '{tc.name}' not found in catalog.")
                args = suite._fill_args_with_defaults(tool.tool, tc.args)
                filled.append((tc.name, args))

            evaluation = case.evaluate(filled)

            return {
                "name": case.name,
                "input": case.user_message,
                "expected_tool_calls": [
                    {"name": tc.name, "args": tc.args}
                    for tc in case.expected_tool_calls
                ],
                "predicted_tool_calls": [
                    {"name": name, "args": args} for name, args in filled
                ],
                "evaluation": evaluation,
            }

    tasks = [sem_task(case) for case in suite.cases]
    results["cases"] = await asyncio.gather(*tasks)
    return results
