# feat(evals): add InferenceBackend protocol for provider-agnostic eval runs

## Summary

- Adds `InferenceBackend` runtime-checkable Protocol to `arcade_evals`
- Adds `OpenAICompatBackend` for any OpenAI-compatible endpoint (OpenAI, Gemini, Together, Groq, Ollama, etc.)
- Adds `AnthropicBackend` wrapping the Anthropic Messages API
- Extends `EvalSuite.run()` with an optional `backend=` keyword argument
- **100% backwards compatible**: existing `suite.run(client, model)` works unchanged

## Motivation

`arcade_evals` currently supports two inference providers via a closed enum (`"openai" | "anthropic"`). Agent developers who evaluate against other providers — Google Gemini, Together AI, Groq, local models via Ollama — have no way to plug into the eval framework without monkey-patching `EvalSuite.run()` or reimplementing the evaluation loop.

This came up while building an agent that uses Gemini via Google's OpenAI-compatible endpoint. The eval framework's assumptions (hardcoded `seed=42`, tool names passed as strings, `strict: true` in schemas) all broke against Gemini's endpoint. Each provider has its own quirks:

| Provider | `seed` | `strict` | `additionalProperties` | Tool name format |
|----------|--------|----------|----------------------|-----------------|
| OpenAI | Yes | Yes | Yes | Any |
| Gemini | No | No | No | No dots |
| Together | No | Yes | Yes | Any |
| Anthropic | N/A | N/A | N/A | Different schema |

Rather than adding provider-specific branches to `run()`, this PR introduces a `Protocol` that lets each provider handle its own quirks.

## Usage

```python
from openai import AsyncOpenAI
from arcade_evals import EvalSuite, OpenAICompatBackend

# ── Gemini (no seed, no strict) ────────────────────────────────
client = AsyncOpenAI(
    api_key=os.environ["GOOGLE_API_KEY"],
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)
backend = OpenAICompatBackend(client, model="gemini-2.5-flash", seed=None, strict=False)
results = await suite.run(backend=backend)

# ── Standard OpenAI (defaults work) ────────────────────────────
backend = OpenAICompatBackend(AsyncOpenAI(), model="gpt-4o")
results = await suite.run(backend=backend)

# ── Anthropic ───────────────────────────────────────────────────
from anthropic import AsyncAnthropic
from arcade_evals import AnthropicBackend

backend = AnthropicBackend(AsyncAnthropic(), model="claude-sonnet-4-20250514")
results = await suite.run(backend=backend)

# ── Custom provider ─────────────────────────────────────────────
class MyBackend:
    @property
    def model_name(self) -> str:
        return "my-model"

    async def call_with_tools(self, messages, tool_names, catalog):
        # Your inference logic here
        ...

results = await suite.run(backend=MyBackend())
```

## Design Decisions

**Protocol over ABC.** Uses `typing.Protocol` with `@runtime_checkable` so users can implement backends without inheriting from an arcade_evals base class. Duck typing > class hierarchies.

**Single `OpenAICompatBackend` with knobs.** Instead of separate `OpenAIBackend`, `GeminiBackend`, `TogetherBackend` classes, one configurable dataclass handles all OpenAI-compatible providers. The `seed` and `strict` parameters are the meaningful differences — no need for a class hierarchy.

**Keyword-only `backend=`.** Added as keyword-only to avoid ambiguity with the existing positional `client` and `model` parameters. When `backend` is provided, the built-in provider logic is bypassed entirely.

**Name mapping via reverse dict.** Each backend builds a `name_map` (LLM-facing normalized name → catalog FQN) so tool call resolution works regardless of how the provider transforms tool names. This avoids relying on environment variables or global state.

## Files Changed

| File | Change |
|------|--------|
| `arcade_evals/_backend.py` | **NEW** — Protocol, OpenAICompatBackend, AnthropicBackend |
| `arcade_evals/eval.py` | Add `backend=` kwarg to `run()`, add `_run_with_backend()` |
| `arcade_evals/__init__.py` | Export `InferenceBackend`, `OpenAICompatBackend`, `AnthropicBackend` |

## Test Plan

- [ ] Existing tests pass unchanged (backwards compatibility)
- [ ] `OpenAICompatBackend` with mocked `AsyncOpenAI` client returns correct tool calls
- [ ] `OpenAICompatBackend(seed=None, strict=False)` strips `seed` from request and `strict`/`additionalProperties` from schemas
- [ ] `AnthropicBackend` with mocked `AsyncAnthropic` client parses `tool_use` blocks
- [ ] Custom class satisfying `InferenceBackend` protocol works with `suite.run(backend=...)`
- [ ] `suite.run()` with neither `client` nor `backend` raises `ValueError`
- [ ] `suite.run(backend=...)` returns same result shape as `suite.run(client, model)`
- [ ] Tool name resolution: LLM returns `BossBattle_MyTool`, correctly maps back to `BossBattle.MyTool` in catalog

---

*Built while developing [BossBattle](https://github.com/...), an AI incident response agent that uses Arcade's MCP Gateway with Gemini inference. The eval framework worked great for defining test cases and scoring — we just needed a way to point it at our model.*
