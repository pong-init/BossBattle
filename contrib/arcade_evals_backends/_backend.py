"""Provider-agnostic inference backends for arcade_evals.

EvalSuite.run() currently supports two built-in providers via a closed
``ProviderName`` literal ("openai" | "anthropic"). This module introduces
an ``InferenceBackend`` Protocol that enables running evals against *any*
LLM provider — including Google Gemini, Together AI, Groq, local Ollama,
or any other OpenAI-compatible endpoint.

Quick start::

    from openai import AsyncOpenAI
    from arcade_evals import OpenAICompatBackend

    # Gemini via Google's OpenAI-compatible endpoint
    client = AsyncOpenAI(
        api_key=os.environ["GOOGLE_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    backend = OpenAICompatBackend(client, model="gemini-2.5-flash", seed=None, strict=False)
    results = await suite.run(backend=backend)

    # Standard OpenAI (defaults: seed=42, strict=True)
    backend = OpenAICompatBackend(AsyncOpenAI(), model="gpt-4o")
    results = await suite.run(backend=backend)

This file is intended to live at ``arcade_evals/_backend.py`` in the
ArcadeAI/arcade-ai monorepo (libs/arcade-evals/arcade_evals/).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from arcade_core.catalog import ToolCatalog
from arcade_core.converters.openai import to_openai
from arcade_core.converters.utils import normalize_tool_name


# ── Data types ─────────────────────────────────────────────────────────


@dataclass
class ToolCallResult:
    """A parsed tool call from an LLM response.

    Attributes:
        name: Tool name compatible with ``ToolCatalog.get_tool_by_name()``.
        args: Parsed argument dictionary.
    """

    name: str
    args: dict[str, Any]


# ── Protocol ───────────────────────────────────────────────────────────


@runtime_checkable
class InferenceBackend(Protocol):
    """Interface for LLM inference providers used in evals.

    Each backend is responsible for:

    * Converting tool definitions to the provider's expected format
    * Sending the chat completion request with appropriate parameters
    * Parsing tool calls from the provider's response format
    * Mapping tool names back to catalog-compatible identifiers

    The returned ``ToolCallResult.name`` values must work with
    ``ToolCatalog.get_tool_by_name()`` and ``compare_tool_name()``
    in evaluation scoring.
    """

    @property
    def model_name(self) -> str:
        """The model identifier for results tracking."""
        ...

    async def call_with_tools(
        self,
        messages: list[dict[str, Any]],
        tool_names: list,
        catalog: ToolCatalog,
    ) -> list[ToolCallResult]:
        """Send a chat completion request with tools and return parsed tool calls.

        Args:
            messages: Conversation messages in OpenAI format.
            tool_names: ``FullyQualifiedName`` objects from the catalog.
            catalog: The ``ToolCatalog`` for tool schema retrieval.

        Returns:
            Parsed tool calls with catalog-compatible names.
        """
        ...


# ── Shared helpers ─────────────────────────────────────────────────────


def _build_openai_schemas(
    tool_names: list, catalog: ToolCatalog
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Convert catalog tools to OpenAI function schemas with a reverse name map.

    Returns:
        A tuple of ``(schemas, name_map)`` where ``name_map`` maps the
        LLM-facing normalized name (e.g. ``"Google_Search"``) back to
        the catalog's FQN string (e.g. ``"Google.Search"``).
    """
    schemas: list[dict[str, Any]] = []
    name_map: dict[str, str] = {}
    for fqn in tool_names:
        tool = catalog[fqn]
        schema = to_openai(tool)
        llm_name = schema["function"]["name"]
        name_map[llm_name] = str(fqn)
        schemas.append(schema)
    return schemas, name_map


def _parse_openai_response(response: Any) -> list[tuple[str, dict[str, Any]]]:
    """Extract ``(name, args)`` tuples from an OpenAI-format chat completion."""
    results: list[tuple[str, dict[str, Any]]] = []
    message = response.choices[0].message
    if message.tool_calls:
        for tc in message.tool_calls:
            results.append((tc.function.name, json.loads(tc.function.arguments)))
    return results


def _resolve_names(
    raw_calls: list[tuple[str, dict[str, Any]]], name_map: dict[str, str]
) -> list[ToolCallResult]:
    """Map LLM-facing tool names back to catalog-compatible FQN strings."""
    return [
        ToolCallResult(name=name_map.get(name, name), args=args)
        for name, args in raw_calls
    ]


# ── Backend implementations ────────────────────────────────────────────


@dataclass
class OpenAICompatBackend:
    """Backend for any OpenAI-compatible endpoint.

    Works with OpenAI, Google Gemini, Together AI, Groq, Fireworks,
    local Ollama, and any other provider that exposes the
    ``/chat/completions`` endpoint with tool calling support.

    Provider-specific behavior is controlled via constructor parameters:

    * **OpenAI**: ``seed=42, strict=True`` (defaults)
    * **Gemini**: ``seed=None, strict=False``
    * **Together/Groq**: ``seed=None, strict=True``

    Args:
        client: An ``AsyncOpenAI``-compatible client instance.
        model: The model identifier string.
        seed: Seed for reproducibility. Set ``None`` for providers
            that don't support it (Gemini, Together, etc.).
        strict: Whether to keep ``strict: true`` and
            ``additionalProperties: false`` in tool schemas. Set
            ``False`` for providers that reject strict-mode artifacts.
        user: Optional user identifier for audit logging.
    """

    client: Any
    model: str
    seed: int | None = 42
    strict: bool = True
    user: str | None = "eval_user"

    @property
    def model_name(self) -> str:
        return self.model

    async def call_with_tools(
        self,
        messages: list[dict[str, Any]],
        tool_names: list,
        catalog: ToolCatalog,
    ) -> list[ToolCallResult]:
        schemas, name_map = _build_openai_schemas(tool_names, catalog)

        if not self.strict:
            for schema in schemas:
                func = schema.get("function", {})
                func.pop("strict", None)
                params = func.get("parameters", {})
                params.pop("additionalProperties", None)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tool_choice": "auto",
            "tools": schemas,
            "stream": False,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed
        if self.user is not None:
            kwargs["user"] = self.user

        response = await self.client.chat.completions.create(**kwargs)
        return _resolve_names(_parse_openai_response(response), name_map)


@dataclass
class AnthropicBackend:
    """Backend for the Anthropic Messages API.

    Converts tool schemas to Anthropic's format and parses
    ``tool_use`` content blocks from the response.

    Args:
        client: An ``AsyncAnthropic`` client instance.
        model: The model identifier string.
        max_tokens: Maximum tokens for the response.
    """

    client: Any
    model: str
    max_tokens: int = 4096

    @property
    def model_name(self) -> str:
        return self.model

    async def call_with_tools(
        self,
        messages: list[dict[str, Any]],
        tool_names: list,
        catalog: ToolCatalog,
    ) -> list[ToolCallResult]:
        from arcade_core.converters.anthropic import to_anthropic

        # Build Anthropic tool schemas with reverse name map
        schemas: list[dict[str, Any]] = []
        name_map: dict[str, str] = {}
        for fqn in tool_names:
            tool = catalog[fqn]
            schema = to_anthropic(tool)
            name_map[schema["name"]] = str(fqn)
            schemas.append(schema)

        # Extract system message
        system_message = ""
        api_messages = messages
        if messages and messages[0].get("role") == "system":
            system_message = messages[0]["content"]
            api_messages = messages[1:]

        # Convert to Anthropic message format
        anthropic_messages = []
        for msg in api_messages:
            anthropic_messages.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_message,
            messages=anthropic_messages,
            tools=schemas,
        )

        results: list[ToolCallResult] = []
        for block in response.content:
            if block.type == "tool_use":
                catalog_name = name_map.get(block.name, block.name)
                results.append(ToolCallResult(name=catalog_name, args=block.input))
        return results
