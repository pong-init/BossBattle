# Session 2: The Observability Saga

**AI Assistant:** Claude Opus 4.6 (via Claude Code CLI)
**Duration:** ~3 hours
**What happened:** Built a 9-panel Grafana dashboard with OTel → Prometheus → Grafana + Tempo. Discovered that traces != metrics, fought Prometheus's `rate()` on batch workloads, and debugged a Docker networking issue caused by adding Tempo.

---

## The Naive Assumption

The build plan allocated "~1 hour" for observability. The actual plan said I could "generate the whole observability stack with a single prompt." Here's what actually happened.

---

## Traces != Metrics

The first discovery was fundamental: OpenTelemetry traces and Prometheus metrics are two completely different data types, and having one doesn't give you the other.

> **Me:** [Shared my OTel implementation and asked why Grafana showed "No data"]
>
> **Claude:** You're exporting traces to the OTel Collector, but Prometheus scrapes metrics. Traces contain timing data embedded in spans — but Prometheus can't query spans. You need a **spanmetrics connector** in the collector pipeline to derive metrics (counters, histograms) from trace spans.

This was the core architectural insight: the OTel Collector needed a `spanmetrics` connector that watches the trace pipeline and emits derived metrics into the metrics pipeline.

```yaml
# Before: traces go one way, metrics go another, never the twain shall meet
pipelines:
  traces:
    receivers: [otlp]
    exporters: [otlp]   # → Tempo
  metrics:
    receivers: [otlp]
    exporters: [prometheus]

# After: spanmetrics bridges traces → metrics
connectors:
  spanmetrics:
    histogram:
      explicit:
        buckets: [5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s]

pipelines:
  traces:
    receivers: [otlp]
    exporters: [otlp, spanmetrics]   # spanmetrics taps the trace stream
  metrics:
    receivers: [otlp, spanmetrics]   # metrics come from both OTLP and span-derived
    exporters: [prometheus]
```

**What I learned:** This gap is exactly why the roadmap recommends Arcade ship native OTel export. Every developer building agent observability hits this wall.

---

## The Cardinality Trap — Gemini Catches Claude's Mistake

I was using Gemini as a parallel advisor throughout this session. When I shared Claude's initial plan for the spanmetrics connector, Gemini caught a critical error:

> **Me:** [Shared Claude's plan with Gemini for review]
>
> **Gemini's critique:** "Claude suggests adding `gen_ai.usage.prompt_tokens` as a dimension in the spanmetrics connector. Be careful here. In Prometheus, 'dimensions' become labels. If you have a dimension for every unique token count (e.g., prompt_tokens=102, 103, 104), you will literally crash your Prometheus instance with a Cardinality Explosion. You don't want the number of tokens to be a label; you want it to be the Value of the metric."
>
> **Claude:** [after seeing Gemini's feedback] "Gemini's right on the cardinality point — that was a real mistake in my suggestion. Token counts go as the **value** of a Counter metric via MeterProvider, not as a spanmetrics dimension."

This was a genuine multi-model collaboration moment: Claude designed the architecture, Gemini caught a production-breaking error in the plan, and the final implementation was better for it.

---

## MeterProvider: The Missing Piece

The second discovery: OpenLLMetry's `LangchainInstrumentor` can emit metrics natively — but only if you configure a `MeterProvider`. Without it, you get traces only. With it, you get `gen_ai_client_operation_duration_seconds` and `gen_ai_client_token_usage` for free.

> **Claude:** The OpenLLMetry `LangchainInstrumentor` is already emitting both `gen_ai_client_operation_duration_seconds` and `gen_ai_client_token_usage` as proper metrics — we don't even need the custom `TokenUsageProcessor` because the instrumentor handles it natively.
>
> **Me:** Wait, so we wrote a custom token processor for nothing?
>
> **Claude:** Yes. When a `MeterProvider` is configured, OpenLLMetry handles it automatically. The custom `TokenUsageProcessor` is redundant. Let me simplify `instrument.py`.

We deleted ~30 lines of custom code. The lesson: check what your instrumentation library already does before building custom processors.

### The Four Metric Sources

| Metric | Source | What it gives us |
|--------|--------|------------------|
| `gen_ai_client_operation_duration_seconds` | OpenLLMetry (native) | LLM call latency |
| `gen_ai_client_token_usage` | OpenLLMetry (native) | Token usage (input/output) |
| `traces_span_metrics_calls_total` | Spanmetrics connector | Call counts per span |
| `traces_span_metrics_duration_milliseconds` | Spanmetrics connector | Latency per span/node |

---

## The Collector Crash

First real debugging cycle. After configuring spanmetrics, the OTel Collector crashed on startup.

> **Claude:** The `spanmetrics` connector already includes `service.name` implicitly — adding it as an explicit dimension causes a conflict.

Fixed by removing explicit dimensions. Then `span.name` caused the same issue. The spanmetrics connector includes both service name and span name by default — no explicit configuration needed.

---

## The First Dashboard

After fixing the collector, we ran all 4 incidents and got data flowing. The first Grafana screenshot showed 6 of 8 panels working:

> **Claude:** 6 of 8 panels are live. Here's the read:
> - **Tool Calls** — Exactly right: 4 GitHub searches (all 404'd), 4 Linear tickets, 4 Slack messages, 2 emails (P1 incidents only). The routing logic is proven.
> - **Error Rate: 6.45%** — That's the GitHub 404s. Genuine signal.
> - **Workflow Runs: 4** — All incidents processed.
>
> **Two "No data" panels to fix:**
> - **LLM Call Latency** — The `rate()` query needs continuous data; a one-shot run produces a flat counter that `rate()` turns into 0/0 = NaN.
> - **Token Usage** — Label mismatch: `job="bossbattle-agent"` vs `exported_job="bossbattle-agent"`.

---

## Prometheus rate() vs. Batch Workloads

This was the subtlest issue. Prometheus's `rate()` function calculates per-second rates from counter increases over time. But BossBattle runs as a batch — 4 incidents, done. The counter goes from 0 to N in one scrape interval and never moves again.

`rate()` on a flat counter = `0/0` = `NaN`.

> **Claude:** Changed from `rate(sum)/rate(count)` (needs continuous data) to `sum/count` (works with one-shot). Also fixed `job` → `exported_job` — Prometheus renames the label when it conflicts with its own scrape job name.

This fix applied to three panels: LLM Call Latency, Node Latency, and E2E Workflow Duration. Also had to change panel titles from "p95" to "avg" since we were now computing `sum/count` (averages) instead of `histogram_quantile` (percentiles).

---

## Tempo Breaks Everything

At some point during the session, I separately added Tempo (distributed tracing backend) to the docker-compose stack. This caused a cascade of failures:

1. Adding the Tempo container restarted the stack, wiping Prometheus's in-memory data
2. The dashboard JSON got corrupted — duplicate closing structures from a bad merge when adding the Tempo panel
3. Most critically: Grafana's `networks: - observability` got dropped from the docker-compose config

That last one was the hardest to diagnose.

> **Me:** nope [screenshot showing all panels with red error triangles]
>
> **Claude:** The red triangles mean Grafana is getting errors from the datasource, not just empty results. Let me check if Grafana can actually reach Prometheus inside Docker.
>
> [investigates]
>
> **Claude:** **502 Bad Gateway** — Grafana can't reach Prometheus. When Tempo was added, the `networks` block was removed from the `grafana` service. Grafana is on the default network, not `observability`, so it can't resolve `prometheus:9090` or `tempo:3200`.

The fix was one line in docker-compose.yml: re-adding `networks: - observability` to the Grafana service.

> **Me:** hell yeah. you my friend are a regular detective pikachu

---

## The Final Dashboard

After the networking fix, all 9 panels lit up:

| Panel | Value | What it tells us |
|-------|-------|------------------|
| **E2E Workflow Duration** | 13.1s | Incident fully triaged in under 15 seconds |
| **LLM Call Latency** | 805ms | Gemini averaging under a second per call |
| **Token Usage** | 9.5K in / 809 out | Input-heavy (big prompts), lean outputs |
| **Error Rate** | 6.25% | The GitHub 404s (expected, known platform bug) |
| **Tool Calls** | 1 each per incident | Exactly right: GitHub, Linear, Slack, Email |
| **Spans/sec** | 1.07 | Reasonable for batch of 4 |
| **Node Latency** | Per-node breakdown | triage, gather_context, create_ticket, notify_team |
| **Workflow Runs** | 4 | All incidents processed |
| **Trace Search** | Tempo integration | Click-through from dashboard to individual traces |

---

## What This Session Taught Me About the Product

The observability stack took ~3 hours instead of the planned 1 hour. Every piece of friction became roadmap evidence:

1. **Traces != metrics is non-obvious.** Most developers assume OTel traces automatically become Prometheus metrics. They don't. Arcade should bridge this gap.

2. **The raw ingredients exist in open source.** OpenLLMetry, spanmetrics connector, Prometheus, Grafana — all work. What's missing is someone connecting them into a seamless experience. That someone should be Arcade.

3. **Arcade sits on the most valuable telemetry data in the agent stack.** Every tool call flows through the Gateway. Emitting OTLP traces from that chokepoint would eliminate the need for developer-side instrumentation entirely.

This became the centerpiece of the Month 2 roadmap: "Ship native OTel export from the Gateway."
