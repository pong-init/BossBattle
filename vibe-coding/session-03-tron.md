# Session 3: From HITL to Tron — The Pivot That Changed Everything

**AI Assistant:** Claude Opus 4.6 (via Claude Code CLI)
**Duration:** ~4 hours
**What happened:** Started planning a human-in-the-loop feature, pivoted to Arcade's Contextual Access after reading the docs, named it after an arcade game, and built a config-driven policy engine with 26 passing tests.

---

## It Started With a Simple Question

> **Me:** what would it take to be able to chat with BossBattle using Slack or an email reply as the input?

Claude broke this down into two parts: an always-on server to receive events, and a "parse" node to convert freeform text into structured `Incident` objects. But I had something different in mind.

> **Me:** i was just thinking about adding a human in the loop, basically after the linear issue is created and i receive the email or when the channel gets the slack notif

This reframed the problem entirely. The agent already sends Slack messages and emails — I just needed it to pause and wait for a reply. Claude immediately identified LangGraph's `interrupt()` primitive as the right fit:

> **Claude:** LangGraph actually has a primitive built for exactly this: `interrupt()`. After `notify_team` posts to `#incidents` and emails the VP, the graph hits `interrupt()`. State gets checkpointed (you already have `MemorySaver`). The process yields control. When the human replies, you resume the graph with their input via `Command(resume=...)`.

Two pieces: (1) graph-side interrupt + human_review node (~50 lines), and (2) a Slack Bolt listener to catch replies and wake the graph.

> **Me:** let's do both pieces, why not?

Claude entered plan mode and started designing the full implementation. But then I had a different idea.

---

## The Pivot

I'd been reading Arcade's docs and found their Contextual Access feature — a webhook-based governance layer with three hooks (access, pre-execution, post-execution).

> **Me:** this is a fine plan, but i'm debating between doing this or trying out contextual access: https://docs.arcade.dev/en/guides/contextual-access which do you think would make the bossbattle agent more compelling?

Claude's recommendation was decisive:

> **Claude:** For a PM take-home at Arcade specifically, Contextual Access is the stronger play. HITL is impressive but Arcade-agnostic — the interrupt + Slack Bolt implementation is all LangGraph and Slack. Any tool-calling framework could do this. Contextual Access is Arcade's enterprise differentiator. Building a demo around it signals you understand what Arcade is actually selling.

This was the right call. HITL would have demonstrated agent engineering skill. Contextual Access demonstrated product intuition about what Arcade is.

---

## The Config-Driven Insight

Then came the conversation that shaped the entire design:

> **Me:** most policy enforcement engines i've seen are config based, because the people that know the policy best are usually not great coders. how does that insight play into things here?

> **Claude:** That's a sharp observation, and it changes the shape of what you'd build. The Arcade docs show you writing a webhook server in Go/Python with policies hardcoded in application logic. That's a developer's answer. But the people who actually define "P3 incidents can't trigger VP emails" or "redact customer IPs from Slack posts" are security engineers, compliance leads, SREs — they think in rules and config, not in FastAPI route handlers.
>
> The real-world pattern is: declarative policy config + generic enforcement engine. That's what OPA/Rego does, what AWS IAM JSON policies do, what Kubernetes RBAC YAML does. The code is the plumbing. The value is in the policy expression layer.

This changed the design from "write a webhook server" to "build a config-driven policy engine." The YAML file becomes the centerpiece — readable by security teams, auditable, version-controlled. The server is generic plumbing.

> **Me:** sick, yes let's plan it

---

## Naming It

During the planning phase, the name question came up. The initial plan used a placeholder.

> **Claude:** [Proposed "Aegis" — mythical shield, fits the theme]
>
> **Me:** can you think of something arcade related?
>
> **Claude:** **Checkpoint** — In gaming: a save point where progress is validated. In security: a control point where traffic is inspected. Triple meaning. **Coin Gate** — You need a coin to pass. Every tool call costs a "coin" of authorization.
>
> **Me:** try harder - maybe a video game that was all about protection or shielding?
>
> **Claude:** **Missile Command** (Atari, 1980) — you intercept incoming threats before they reach their targets. That's literally what a pre-execution hook does.
>
> **Defender** (Williams, 1981) — you defend a planet from alien abductors. Strong name, but less direct as a metaphor.
>
> **Tron** (Bally Midway, 1982) — In the movie, Tron is a security program that monitors and protects the system. The villain? The **MCP** — Master Control Program. Here, Tron is the security program governing tool calls flowing through Arcade's **MCP** (Model Context Protocol). The naming collision is too perfect.

> **Me:** Tron

The MCP connection sealed it — in the 1982 film, Tron fights the MCP. In our system, Tron governs tool calls flowing through Arcade's MCP. Security program vs. control program, 44 years later.

---

## Building Tron

Claude fetched Arcade's complete OpenAPI schema for the webhook contract and designed the system:

### The Architecture
```
BossBattle Agent → Arcade MCP Gateway → [Tron webhook] → Tool executes
                                              ↓
                                     policies.yaml (YAML rules)
                                     engine.py (generic evaluator)
                                     server.py (FastAPI plumbing)
```

The agent code is unchanged (except adding incident ID to Slack messages). Policy is fully externalized.

### The Centerpiece: policies.yaml

Every rule has a plain-English `description`. Conditions use dot-notation field paths, regex matching, and declarative actions. Non-coders edit this file, not Python.

```yaml
pre:
  rules:
    - description: "Block email escalation for P3/P4 incidents"
      tool: "Gmail_SendEmail"
      condition:
        field: "inputs.subject"
        matches: "\\[(P3|P4)\\s*(INCIDENT|incident)\\]"
      action: block
      error_message: >
        Policy violation: P3/P4 incidents do not escalate to email.
        Only P1 and P2 incidents trigger VP notification.

    - description: "Force Slack messages to #incidents channel"
      tool: "Slack_SendMessage"
      condition:
        field: "inputs.channel_name"
        not_equals: "#incidents"
      action: override
      override_inputs:
        channel_name: "#incidents"
```

### The Engine

`PolicyEngine` loads `policies.yaml` at init, evaluates rules against incoming requests:

- `evaluate_access()` — who can see which tools (user ID matching)
- `evaluate_pre()` — validate inputs before execution (block or override)
- `evaluate_post()` — sanitize outputs after execution (regex redaction)

Key helper: `_resolve_field("inputs.subject", request)` navigates dot-paths against Pydantic models + nested dicts. This is what makes YAML field paths work naturally.

### The Server

Four routes, bearer token auth, logging. Under 80 lines of actual logic. Pure plumbing.

---

## Tests: 25/26, Then 26/26

First run: 25 of 26 tests passed. One failure:

```
assert "incident ID" in result.error_message.lower()
```

The `.lower()` call converts "ID" to "id", so the assertion needed to check for "incident id" not "incident ID". One-line fix, all 26 passing.

---

## Verification with curl

After the tests, we verified the server with live requests:

```bash
# Health check
$ curl localhost:4242/health
{"status": "healthy"}

# P3 email → blocked
$ curl -X POST localhost:4242/pre -d '{"tool": {"name": "Gmail_SendEmail"}, "inputs": {"subject": "[P3 INCIDENT] Slow queries"}}'
{"code": "CHECK_FAILED", "error_message": "Policy violation: P3/P4 incidents do not escalate to email..."}

# P1 email → allowed
$ curl -X POST localhost:4242/pre -d '{"tool": {"name": "Gmail_SendEmail"}, "inputs": {"subject": "[P1 INCIDENT] DB down"}}'
{"code": "OK"}

# Post-hook with PII → redacted
$ curl -X POST localhost:4242/post -d '{"output": "Contact john@corp.com at 10.0.1.42 for token ghp_AAAA..."}'
{"code": "OK", "override": {"output": "Contact [EMAIL_REDACTED] at [IP_REDACTED] for token [GITHUB_TOKEN_REDACTED]..."}}
```

---

## What This Session Demonstrated

1. **Pivoting based on audience.** HITL was the technically interesting choice. Contextual Access was the strategically right choice for an Arcade PM role. The AI helped evaluate the tradeoff, but the decision was mine.

2. **Config-driven design as a product insight.** The shift from "write a webhook" to "build a policy engine with YAML config" came from my experience with enterprise policy tools. Claude implemented the architecture, but the design insight was human.

3. **The MCP naming connection.** Sometimes the best product decisions come from unexpected pattern-matching. A 1982 arcade game about a security program fighting the MCP turned out to be the perfect name for a security program governing Arcade's MCP.

4. **Zero agent code changes.** The agent doesn't know Tron exists. Policy is fully externalized. This is the key architectural insight: governance should be a layer, not embedded logic.
