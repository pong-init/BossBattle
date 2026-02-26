"""
Patch for EvalSuite.run() — adds backwards-compatible ``backend=`` kwarg.

This file shows the exact changes needed in ``arcade_evals/eval.py``
to support custom InferenceBackend implementations alongside the
existing ``(client, model)`` API.

Target file: libs/arcade-evals/arcade_evals/eval.py in ArcadeAI/arcade-ai
"""

# ─────────────────────────────────────────────────────────────────────
# CHANGE 1: Add import at top of eval.py
# ─────────────────────────────────────────────────────────────────────

# from arcade_evals._backend import InferenceBackend  # noqa: F401


# ─────────────────────────────────────────────────────────────────────
# CHANGE 2: Modify EvalSuite.run() signature and add early branch
# ─────────────────────────────────────────────────────────────────────

# BEFORE (line ~609):
#
#     async def run(self, client: AsyncOpenAI, model: str) -> dict[str, Any]:
#
# AFTER:

async def run(
    self,
    client=None,  # was: client: AsyncOpenAI
    model: str = "",
    *,
    backend: "InferenceBackend | None" = None,
) -> "dict[str, Any]":
    """
    Run the evaluation suite.

    Can be called in two ways:

    1. Built-in path (backwards compatible)::

        results = await suite.run(client=client, model="gpt-4o")

    2. Custom backend path::

        from arcade_evals import OpenAICompatBackend
        backend = OpenAICompatBackend(client, model="gemini-2.5-flash", seed=None, strict=False)
        results = await suite.run(backend=backend)

    Args:
        client: An AsyncOpenAI client instance (built-in path).
        model: The model identifier (built-in path).
        backend: An InferenceBackend implementation (custom path).
            When provided, ``client`` and ``model`` are ignored.

    Returns:
        A dictionary containing the evaluation results.
    """
    import asyncio

    # ── Custom backend path ──────────────────────────────────────
    if backend is not None:
        return await self._run_with_backend(backend)

    # ── Built-in path (existing code, unchanged) ─────────────────
    if client is None:
        raise ValueError(
            "Provide either (client, model) or backend=InferenceBackend."
        )

    # ... rest of existing run() method stays exactly as-is ...
    pass


# ─────────────────────────────────────────────────────────────────────
# CHANGE 3: Add _run_with_backend() method to EvalSuite
# ─────────────────────────────────────────────────────────────────────

async def _run_with_backend(self, backend: "InferenceBackend") -> "dict[str, Any]":
    """Run the evaluation suite using a custom InferenceBackend.

    Mirrors the structure of the built-in run() method but delegates
    the LLM call to the backend, making provider-specific concerns
    (schema format, supported params, response parsing) the backend's
    responsibility.
    """
    import asyncio

    results: "dict[str, Any]" = {
        "model": backend.model_name,
        "rubric": self.rubric,
        "cases": [],
    }

    semaphore = asyncio.Semaphore(self.max_concurrent)
    tool_names = list(self.catalog.get_tool_names())

    async def sem_task(case) -> "dict[str, Any]":
        async with semaphore:
            # Build messages
            messages = [{"role": "system", "content": case.system_message}]
            messages.extend(case.additional_messages)
            messages.append({"role": "user", "content": case.user_message})

            # Delegate to backend
            tool_calls = await backend.call_with_tools(
                messages, tool_names, self.catalog
            )

            # Fill defaults and build evaluation input
            filled_actual_tool_calls = []
            for tc in tool_calls:
                tool = self.catalog.get_tool_by_name(tc.name)
                if tool is None:
                    raise ValueError(f"Tool '{tc.name}' not found in catalog.")
                args = self._fill_args_with_defaults(tool.tool, tc.args)
                filled_actual_tool_calls.append((tc.name, args))

            # Evaluate (reuses existing scoring logic unchanged)
            evaluation = case.evaluate(filled_actual_tool_calls)

            return {
                "name": case.name,
                "input": case.user_message,
                "expected_tool_calls": [
                    {"name": tc.name, "args": tc.args}
                    for tc in case.expected_tool_calls
                ],
                "predicted_tool_calls": [
                    {"name": name, "args": args}
                    for name, args in filled_actual_tool_calls
                ],
                "evaluation": evaluation,
            }

    tasks = [sem_task(case) for case in self.cases]
    results["cases"] = await asyncio.gather(*tasks)
    return results


# ─────────────────────────────────────────────────────────────────────
# CHANGE 4: Update __init__.py exports
# ─────────────────────────────────────────────────────────────────────

# Add to arcade_evals/__init__.py:
#
#   from ._backend import AnthropicBackend, InferenceBackend, OpenAICompatBackend
#
# Add to __all__:
#
#   "AnthropicBackend",
#   "InferenceBackend",
#   "OpenAICompatBackend",
