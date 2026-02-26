# Session 5: Strategic Synthesis — Roadmap, Positioning, and Root Cause

**AI Assistant:** Gemini (via Antigravity)
**Duration:** ~3 hours
**What happened:** Built the production OTel stack, synthesized the 90-day roadmap, diagnosed the GitHub 404 root cause, and explored Arcade's competitive positioning in the MCP ecosystem.

---

## The Multi-Model Dynamic

This session ran in parallel with Claude's Sessions 1-4. The human orchestrated both agents for different strengths:

- **Claude:** Implementation — wrote the agent, nodes, Tron engine, tests
- **Gemini:** Infrastructure + strategy — built the OTel stack, synthesized strategic insights, reviewed Claude's work

The most valuable collaboration moment: when Claude proposed adding `gen_ai.usage.prompt_tokens` as a dimension in the spanmetrics connector, Gemini caught the **Cardinality Explosion** risk:

> **Gemini:** "Claude suggests adding `gen_ai.usage.prompt_tokens` as a dimension in the spanmetrics connector. Be careful here. In Prometheus, 'dimensions' become labels. If you have a dimension for every unique token count (e.g., prompt_tokens=102, 103, 104), you will literally crash your Prometheus instance with a Cardinality Explosion. You don't want the number of tokens to be a label; you want it to be the Value of the metric."

Claude acknowledged the catch, and the final implementation used token counts as metric *values*, not labels.

---

## Building the Observability Stack

Gemini built the Docker-based OTel stack from scratch: `docker-compose.yml`, `otel-collector.yml`, `instrument.py`, `tempo.yml`, and a 9-panel Grafana dashboard.

The first attempt hit a wall:

> **Me:** grafana loads and the dashboard was created, but no data

> **Gemini:** "Grafana is the 'Glass,' but it requires different 'Databases' for different signals. Prometheus stores Metrics (numbers); Tempo or Jaeger store Traces (spans). You have the Glass and the Metric DB, but you're missing the Trace DB or the bridge to turn those traces into numbers."

> **Me:** does grafana only show metrics? could we do simple trace log views and searches too?

> **Gemini:** "Grafana can do trace searches and log views, but it's just the window — it needs Tempo (for traces) or Loki (for logs) running behind it."

> **Me:** can we just build this?

> **Gemini:** [Deployed Tempo, added the spanmetrics connector, wired the full pipeline, and added a Trace Search panel to the dashboard]

---

## The GitHub 404 Root Cause

Claude noted the GitHub 404 bug in Session 1. In this session, Gemini found the **actual root cause**.

> **Me:** we had assumed that arcade's github tool had a problem with private repos, but i changed the pixelcorp-backend repo to public and it seems like we still got the 404s. what gives?

> **Gemini:** [Queried the GitHub API directly — 200 OK, repo exists and is public. Then dug into the OTel collector debug logs and found the smoking gun:]

```
Client error '404 Not Found' for url
'https://github.com/pong-init/pixelcorp-backend/repos/pong-init/pixelcorp-backend/pulls'
```

> **Gemini:** "See the URL? It's using `github.com` instead of `api.github.com`, and the owner/repo path is doubled. This is a bug in Arcade's `list_pull_requests` tool implementation, not an auth or visibility issue. Public, private, authenticated, unauthenticated — doesn't matter. That URL will always 404."

> **Me:** thanks for looking again. i knew something was off

---

## The "Two-Tier Tool" Discovery

Arcade sent a marketing email promoting their custom tools SDK. The user's reaction surfaced a critical product gap:

> **Me:** the truth is i don't think that arcade shipped it. it's like really, really clunky to add and use tools in the gateway, and there's no telemetry

> **Gemini:** "If you register `BossBattle_MarkResolved` as a custom tool, and it doesn't show up in your traces, you've created a blind spot in your own observability pipeline. You'd have two classes of tools: 'observable native tools' and 'invisible custom tools.' That's worse than not having a Gateway at all."

> **Gemini:** "For this to be real, custom tools need parity with native tools: same auth flow, same OTel spans, same eval harness, same discovery. If custom tools don't get all four, they're second-class citizens — and developers will feel it immediately."

---

## Gateway vs. MCP Server: The Positioning Question

> **Me:** why do you think arcade is pushing the creation of MCP servers themselves, and in a way that seems more aggressive than the gateway? or are they the same thing?

> **Gemini:** [Read both docs pages.] "They're not the same. The Gateway runs in Arcade's cloud and composes tools from the catalog. The MCP Server SDK runs on your machine and lets you create tools. The Gateway is a consumption product; the SDK is a creation product."

> **Gemini:** "They're pushing the SDK harder because they need supply-side growth. The demand side (Gateways) only works if there are enough tools to compose."

> **Me:** i guess the disconnect that i see is that anthropic themselves are pushing MCP registries hard, and remote MCP servers are popping up from all types of major software companies. why is arcade trying to bootstrap a supply side motion that's bigger than them?

> **Gemini:** "Arcade's `MCPApp` is just another wrapper around the same MCP protocol. There's no proprietary advantage in the transport layer. It's commodity infrastructure. Arcade's moat is in three things you experienced firsthand: Auth Aggregation (the Gateway flattened OAuth across 4 tools into one API key), Tool Composition (one endpoint for 5 providers), and the Write Path (most MCP servers are read-only; Arcade's actually create tickets and send emails)."

> **Gemini:** "By pushing `arcade-mcp-server` as a 'build your own' SDK, Arcade is diluting its own positioning. They're saying 'We're a platform' and 'We're a framework' simultaneously."

---

## Crystallizing the Roadmap

The 90-day roadmap emerged through conversation, not a planning document:

> **Me:** now you get it. and the rough 90 day sequence (in month long chunks) feels like:
> 1. lean into growth/usability - there was a gateway assistant MCP and I didn't know about it! dropping into the dashboard is clunky...
> 2. focus on the gateway - as you mentioned earlier, the gateways are the key, and what anthropic ISN'T building...
> 3. ship tron - leverage the leadership position of solving a real dev problem, and using it to catapult ourselves into the c-suite conversation by giving security teams a way to wrangle these scary, pesky agents

> **Gemini:** "That's the roadmap. You just wrote the executive summary in three sentences."

---

## The LiteLLM Partnership Thesis

> **Me:** is there a partner, or even BUY opportunity for LiteLLM or similar?

> **Gemini:** "LiteLLM does exactly what Arcade doesn't: it sits between the agent and the LLM. Combined, you'd own both traffic streams — every prompt and every action in one audit log. LiteLLM is a small team, monetization is thin, and they have no agentic story. Complementary product, acquirable if the market signal is strong enough."

> **Me:** to be clear, the 90 day roadmap is good as-is - expanding to LLM traffic and realizing the agent (not just tool) gateway is further out, and i REALLY like the idea of open source integration/co-partnership to prove out the demand

> **Gemini:** "Totally agree. The 90-day plan is tight and self-contained. The smart move is exactly what you said: prove the demand first with an open-source integration before committing engineering resources or M&A capital."

---

## How Gemini Was Used vs. Claude

| Dimension | Claude (Sessions 1-4) | Gemini (Session 5) |
|---|---|---|
| **Primary role** | Implementation | Infrastructure + Strategy |
| **Code written** | Agent, Tron, evals, tests | OTel stack, Grafana dashboard, instrument.py |
| **Strategic output** | Pivot recommendation (HITL → Tron) | Roadmap synthesis, competitive positioning |
| **Debugging** | Docker networking, test failures | OTel signal gap, GitHub 404 root cause |
| **Review** | Critiqued the deliverable doc | Caught cardinality bug in Claude's spanmetrics plan |

The human's role: orchestrating both agents, making strategic decisions (the Tron pivot, the roadmap sequencing), and connecting insights across sessions that neither agent could see independently.
