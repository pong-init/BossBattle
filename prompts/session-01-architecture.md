# Session 1: Architecture & Initial Build

**AI Assistant:** Claude Opus 4.6 (via Claude Code CLI)
**Duration:** ~4 hours
**What happened:** Planned the agent architecture, built the 4-node LangGraph pipeline, discovered MCP adapters, swapped from OpenAI to Gemini, and contributed a PR to the Arcade eval framework.

---

## Starting Point

I came in with a detailed build plan (`bossbattle-build-plan_1.md` — 1,159 lines) that I'd written with Claude in a previous planning session. The plan specified:

- 4-node LangGraph pipeline (triage → context → ticket → notify)
- `langchain-arcade` for tool integration
- OpenAI GPT-4o as the LLM
- MCP Gateway with Arcade Headers auth
- 4 seeded incidents (P1-P4)

The question was: does the plan survive contact with reality?

---

## The Hallucination Check

Early in the session, Claude scaffolded the 4-node pipeline skeleton. I caught something: the code was written without reading the current Arcade docs or MCP adapter APIs. This was exactly the hallucination risk the build plan had warned about.

> **Me:** [Called out that the skeleton was written without grounding in current docs]

This led to a full rewrite of the tool integration layer, this time grounded in the actual `langchain-mcp-adapters` package API. Lesson: always verify AI-generated code against current docs, especially for fast-moving libraries.

---

## Key Decision: langchain-arcade → MCP Adapters

The original plan called for `langchain-arcade` with `ToolManager(use_interrupts=True)` — Arcade's official LangChain integration. After the grounding exercise, Claude explored the current state of the ecosystem and identified that `langchain-mcp-adapters` provided a cleaner integration path with the MCP Gateway.

> **Claude:** The `langchain-mcp-adapters` package gives you a direct MCP client connection to the Gateway. Instead of `ToolManager` wrapping individual tool servers, you get one `MultiServerMCPClient` pointed at your Gateway URL. All tools load through a single endpoint.

The real "aha" moment: the MCP Gateway URL had been in my `.env` file the entire time but was never actually used in the code. Switching to `langchain-mcp-adapters` eliminated ~100 lines of OAuth/interrupt handling code. The Gateway with Arcade Headers auth just worked.

The switch simplified the entire tool loading story — one URL, one client, all tools. The Gateway's "single endpoint for multiple servers" design aligned perfectly with `langchain-mcp-adapters`.

**What changed:** `langchain-arcade` dependency removed, `langchain-mcp-adapters` added. Tool loading went from per-server configuration to a single MCP client connection.

---

## Key Decision: OpenAI → Gemini (The Model Cascade)

The plan specified GPT-4o. During implementation, I decided to switch to Gemini for faster iteration and to test Arcade's model-agnosticism claim. What followed was a cascade of model attempts:

1. `gemini-2.0-flash` — initial target
2. `gemini-2.5-flash-preview` — tried for newer capabilities
3. `gemini-2.5-flash` — quota exhaustion on the free tier
4. `gemini-2.5-flash-lite` — final working model with paid API key

The model swap itself was straightforward at the LangChain level (`ChatOpenAI` → `ChatGoogleGenerativeAI`). But the eval framework had opinions.

`arcade_evals`'s `suite.run()` hardcoded OpenAI-specific assumptions: string tool names, `seed=42`, `strict:true` in tool definitions. All of these broke with Gemini.

---

## The Eval Framework Contribution (PR #783)

When the eval framework broke with Gemini, Claude and I traced the issue to `arcade_evals`'s tight coupling with OpenAI's tool calling format. Rather than work around it, we contributed a fix upstream.

> **Claude:** The issue is in `_evalsuite/__init__.py` — `suite.run()` constructs tool schemas assuming OpenAI's format. The fix is a provider-agnostic `InferenceBackend` protocol that extracts inference execution behind an interface. Each provider handles its own quirks, eval logic stays universal.
>
> **Me:** Let's do it properly — make it a real PR, not a hack.

The result was ~200 lines of code with zero breaking changes to the existing API:

- `InferenceBackend` protocol with `create_client()` and `execute_inference()` methods
- `OpenAIBackend` (default, preserves existing behavior)
- `GeminiBackend` (new, handles Gemini's tool calling format)
- `suite.run()` accepts an optional `backend` parameter

PR #783 on ArcadeAI/arcade-mcp.

**Insight for the doc:** A platform that's model-agnostic should have model-agnostic evaluation infrastructure. This became evidence for the gap analysis.

### Eval Results

With the backend fix in place, evals ran successfully:

- **Triage accuracy:** 6/7 — the one miss was an infra-down edge case where the LLM chose P2 instead of P1 (itself a useful finding about LLM severity classification behavior)
- **Routing accuracy:** 4/4 — P1/P2 correctly routed to Slack + email, P3/P4 to Slack only

---

## Building the Agent

The actual agent implementation went smoothly once the tooling decisions were made. Claude built:

1. **`agent/models.py`** — Pydantic models for `Incident` and `IncidentState` with LangGraph's `add_messages` reducer
2. **`agent/graph.py`** — StateGraph with 4 nodes, conditional routing (P1/P2 → email, P3/P4 → Slack only), `MemorySaver` checkpointer
3. **`agent/nodes/triage.py`** — LLM-powered severity classification
4. **`agent/nodes/context.py`** — GitHub PR search via `GithubApi_ListPullRequests`
5. **`agent/nodes/ticket.py`** — Linear ticket creation with severity-mapped priority
6. **`agent/nodes/notify.py`** — Slack + conditional Gmail notification
7. **`agent/prompts.py`** — System prompts for each node
8. **`main.py`** — CLI runner loading from `seed/incidents.json`

Each node follows the same pattern: load tools from MCP client, bind to model, invoke with a formatted prompt, extract results into state.

---

## The GitHub 404 Bug

When running the agent, `GithubApi_ListPullRequests` returned 404 on every call regardless of repo visibility. The error looked like a permissions issue.

> **Me:** [Made the repo public thinking it was a visibility problem]
>
> **Claude:** Looking at the OTel trace logs, the request URL is malformed: `github.com/owner/repo/repos/owner/repo/pulls` instead of `api.github.com/repos/owner/repo/pulls`. The owner/repo path is doubled and it's hitting `github.com` instead of `api.github.com`. This is a platform bug in Arcade's GitHub tool, not a permissions issue.

I'd already wasted time making my repo public. The raw 404 with no context caused both me and the LLM to misdiagnose the problem. This became one of the strongest examples in the friction journal and directly informed the "make every error actionable" roadmap item.

---

## Arcade Headers: The Anticipated Problem That Wasn't

The build plan's biggest anticipated friction point was OAuth. I'd planned for 4 separate OAuth interrupts, complex token refresh handling, and auth-related failures. None of that happened.

The MCP Gateway with Arcade Headers auth (API key + user ID in HTTP headers) meant the agent just worked. No interactive auth, no token expiration, no 3am problems. The plan's multi-paragraph section on OAuth interrupt handling turned out to be unnecessary.

**Insight for the doc:** This was a genuine product strength. Credit where it's due — Arcade had already solved the programmatic agent auth problem.

---

## What the Plan Got Right vs. Wrong

| Aspect | Plan Said | Reality |
|--------|-----------|---------|
| Architecture | 4-node LangGraph pipeline | Exactly as planned |
| Tool integration | `langchain-arcade` + `ToolManager` | Switched to `langchain-mcp-adapters` |
| LLM | OpenAI GPT-4o | Switched to Gemini 2.5 Flash |
| Auth | Complex OAuth interrupt handling | Arcade Headers — trivial |
| Seed data | 4 incidents, GitHub commits | Exactly as planned |
| Evals | `arcade_evals` out of the box | Broke with Gemini, required upstream PR |

The architecture held. The integration details didn't. This is a normal outcome for good planning — the structure is right, the specifics change on contact with the tools.
