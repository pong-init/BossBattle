# BossBattle

AI incident response agent that triages production incidents, investigates root causes, creates tickets, and notifies the right people — built on Arcade's MCP Gateway, LangGraph, and Gemini.

## Architecture

```
                         Arcade MCP Gateway
                    ┌──────────────────────────┐
                    │  GitHub  Linear  Slack    │
                    │  Search  Create  Send     │
                    │  Commits Issue   Message  │
                    │          ...    Gmail Send │
                    └──────────┬───────────────┘
                               │
  seed/incidents.json          │ MCP (tool calls)
        │                      │
        ▼                      ▼
  ┌──────────┐   ┌─────────────────────────────────────────────┐
  │ Incident │──▶│              LangGraph Pipeline             │
  │  (JSON)  │   │                                             │
  └──────────┘   │  triage ──▶ gather_context ──▶ create_ticket ──▶ notify_team  │
                 │  (no tools)  (GitHub)          (Linear)        (Slack+Gmail)  │
                 │                                                              │
                 │  Model: gemini-2.5-flash-lite                                │
                 └──────────────────────────────────────────────────────────────┘
```

Each node receives **only the tools it needs** — triage uses pure LLM reasoning with no tools, context gathering gets GitHub tools, ticket creation gets Linear, and notifications get Slack + Gmail.

## How It Works

1. **Triage** — Classifies severity (P1–P4) using structured rules: error rate, affected users, infrastructure status. No tools, pure reasoning.
2. **Gather Context** — Searches GitHub for recent commits, PRs, and risky changes (migrations, config updates) that may explain the incident.
3. **Create Ticket** — Opens a Linear issue with severity, incident details, metrics, and GitHub findings. Maps P1→urgent, P2→high, P3→medium, P4→low.
4. **Notify Team** — Posts to Slack `#incidents` for all severities. P1/P2 also sends email to VP Engineering. P3/P4 are Slack-only.

## Quick Start

### Prerequisites

- Python 3.11+
- [Arcade](https://arcade.dev) account with API key
- Google API key (Gemini)
- Docker (for observability stack, optional)

### Setup

```bash
git clone https://github.com/pong-init/BossBattle.git
cd BossBattle
pip install -e .
cp .env.example .env
# Fill in your keys in .env
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ARCADE_API_KEY` | Arcade API key (bearer token) |
| `GOOGLE_API_KEY` | Google Gemini API key |
| `ARCADE_USER_ID` | Your email for Arcade auth |
| `ARCADE_GATEWAY_URL` | MCP Gateway endpoint (default: `https://api.arcade.dev/mcp/bossbattle-incident`) |
| `PIXELCORP_GITHUB_REPO` | Target repo for GitHub searches (default: `pong-init/pixelcorp-backend`) |
| `VP_ENG_EMAIL` | VP Engineering email for P1/P2 escalation |

### Run

```bash
make run              # Default incident (auth 500s)
make run-all          # All 4 incidents end-to-end
make run-p1           # Database failover (P1)
make run-p2           # Auth 500 errors (P2)
make run-p3           # Slow search (P3)
make run-p4           # CSS rendering (P4)
```

## Sample Incidents

Four production incidents in `seed/incidents.json` spanning the severity spectrum:

| ID | Title | Error Rate | Users | Expected |
|----|-------|-----------|-------|----------|
| INC-2026-0142 | Auth service 500 errors | 47% | 12,000 | P2 |
| INC-2026-0143 | Slow product search | 0.2% | 500 | P3 |
| INC-2026-0144 | CSS rendering on checkout | 0% | 50 | P4 |
| INC-2026-0145 | Database primary failover | 100% | 85,000 | P1 |

A companion script (`seed/seed_github.py`) plants realistic commits in `pixelcorp-backend` — including the OAuth provider migration that the agent identifies as the probable cause for INC-2026-0142.

## Evals

11 test cases validate the agent's decision-making using Arcade's `arcade_evals` framework:

- **Triage evals** (7 cases) — Severity classification including boundary conditions and edge cases
- **Routing evals** (4 cases) — Notification dispatch: P1/P2 get Slack + Email, P3/P4 get Slack only

```bash
make evals            # arcade evals evals/ --details
```

### Provider-Agnostic Backend

The evals run against Gemini via a custom `InferenceBackend` protocol (`evals/backends.py`) that decouples `arcade_evals` from any specific LLM provider. This same abstraction was contributed back upstream as [PR #783](https://github.com/ArcadeAI/arcade-mcp/pull/783).

## Observability

OpenTelemetry instrumentation with a Docker Compose stack:

```
LangChain traces ──▶ OTLP Collector ──▶ Prometheus ──▶ Grafana
                     (gRPC :4317)       (scrape :8888)  (:3000)
```

```bash
make obs-up           # Start Collector + Prometheus + Grafana
make obs-down         # Tear down
```

Grafana is accessible at `http://localhost:3000` with pre-configured Prometheus datasource.

## Project Structure

```
bossbattle/
├── main.py                    # Entry point — CLI, incident loading, graph execution
├── agent/
│   ├── config.py              # MCP client, model, LangGraph config
│   ├── graph.py               # 4-node StateGraph with per-node tool binding
│   ├── models.py              # Incident, IncidentState (Pydantic)
│   ├── prompts.py             # System prompt + per-node instructions
│   └── nodes/                 # triage, context, ticket, notify
├── evals/
│   ├── eval_triage.py         # 7 severity classification test cases
│   ├── eval_routing.py        # 4 notification routing test cases
│   └── backends.py            # InferenceBackend protocol (provider-agnostic)
├── observability/
│   ├── docker-compose.yml     # OTel Collector + Prometheus + Grafana
│   ├── instrument.py          # TracerProvider setup + LangChain auto-instrumentation
│   └── otel-collector.yml     # OTLP receiver and exporter config
├── seed/
│   ├── incidents.json         # 4 sample incidents (P1–P4)
│   └── seed_github.py         # Plants realistic commit history
├── contrib/
│   └── arcade_evals_backends/ # Upstream contribution (PR #783)
└── vibe-coding/
    └── friction-journal.md    # Development friction log
```

## Built With

- [LangGraph](https://langchain-ai.github.io/langgraph/) — Agent orchestration
- [Arcade MCP Gateway](https://arcade.dev) — Tool hosting (GitHub, Linear, Slack, Gmail)
- [Gemini 2.5 Flash Lite](https://ai.google.dev/) — LLM inference
- [arcade_evals](https://github.com/ArcadeAI/arcade-mcp) — Eval framework
- [OpenTelemetry](https://opentelemetry.io/) — Distributed tracing
