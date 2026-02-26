# BossBattle Friction Journal

> Running log of every pain point encountered during the build sprint.
> Frame failures as platform critiques, not personal skill gaps.
> Each entry becomes evidence for the Enterprise Gap Analysis and 90-Day Roadmap.

---

## Format

**[TOOL/SERVICE] — [WHAT HAPPENED]**
> Enterprise critique: [What this means for enterprise adoption]

---

## Entries

**Arcade Dashboard — First-run confusion**
Signed up for Hobby account, landed on dashboard with pre-populated apps and secrets. No guidance on what was mine vs. defaults. No onboarding wizard. Discovered the Gateway AI Assistant completely by accident, hidden behind the manual creation flow.
> Enterprise critique: Time-to-first-value is too long for "sign up and build." The AI Assistant should be the default path, not a hidden option.

**Arcade Dashboard — Tool selection UX**
The "shopping cart" for adding tools shows a count but not which tools are selected. Clicking a green checkmark removes the tool with no undo. Lost my selection multiple times. Two different GitHub servers with no "created by" metadata.
> Enterprise critique: Gateway misconfiguration → support tickets → adoption friction. Review step + undo + search would eliminate this class of error.

**Arcade / GitHub — GithubApi_ListPullRequests 404**
Tool constructs malformed URL: doubles the owner/repo path (`github.com/owner/repo/repos/owner/repo/pulls`) and hits `github.com` instead of `api.github.com`. Returns 404 on every call. I wasted time making my repo public because the 404 looked like a permissions issue. Only found root cause in OTel trace logs.
> Enterprise critique: A raw 404 with no context caused a developer to misdiagnose and "fix" a problem that didn't exist. Every error should tell you what went wrong, why, and what to do next.

**Arcade — Error → resolution paths broken**
When GitHub tool needed a server URL configured, got a notification that didn't link to the settings page. Clicking "Edit" opened a modal where I had to find the error at the bottom, which opened a new tab. Three different UI surfaces to resolve one config issue.
> Enterprise critique: Every error in the platform should answer "what do I do next?" Currently takes 3 clicks across 3 surfaces to fix a one-field config issue.

**Arcade — Gmail auth looping**
The sequence of auth → tool call matters more than expected. Got an opaque error that took 30+ minutes to debug. Not sure if this is a LangChain issue or an Arcade issue — the error gave no indication either way.
> Enterprise critique: Opaque auth errors are the #1 developer frustration with OAuth-based platforms. Auth failures should diagnose and suggest next steps.

**arcade_evals — Model provider assumption**
`suite.run()` hardcodes OpenAI-specific assumptions: string tool names, `seed=42`, `strict:true`. Switching to Gemini 2.5 Flash broke the eval framework entirely. Had to contribute PR #783 with a provider-agnostic `InferenceBackend` protocol.
> Enterprise critique: A model-agnostic platform should have model-agnostic evaluation infrastructure. The eval framework is the first thing enterprise teams reach for to validate agent behavior.

**OTel / Observability — Traces != metrics**
Assumed OTel traces would automatically become Prometheus metrics. They don't. Needed a `spanmetrics` connector to bridge traces → metrics pipeline. This gap added ~2 hours to what was planned as a 1-hour task.
> Enterprise critique: Arcade sits on the most valuable telemetry data in the agent stack — every tool call, every auth flow. None of it is observable without developer-side instrumentation.

**Prometheus — rate() on batch workloads**
`rate()` returns NaN for batch workloads (counters that increment once and stop). BossBattle processes 4 incidents then exits — counters go from 0 to N in one scrape interval. Had to rewrite Grafana queries from `rate(sum)/rate(count)` to `sum/count`.
> Enterprise critique: Most agent workloads are batch/event-driven, not continuous. Default monitoring templates assume continuous traffic patterns.

**Docker — Tempo addition broke Grafana networking**
Adding Tempo to docker-compose.yml accidentally removed `networks: - observability` from the Grafana service. Grafana got isolated on the default Docker network, couldn't resolve `prometheus:9090`. Manifested as red error triangles on all dashboard panels with no useful error message from Grafana.
> Enterprise critique: Infrastructure-as-code changes have non-obvious cascading effects. Grafana's error UX for datasource connectivity issues is unhelpful.

**OTel / Prometheus — Label mismatch (job vs exported_job)**
Prometheus renames the `job` label to `exported_job` when it conflicts with its own scrape job name. Dashboard queries filtering on `job="bossbattle-agent"` matched nothing because the actual label was `exported_job="bossbattle-agent"`. No error, just empty panels.
> Enterprise critique: Silent failures (no data instead of error) are the worst debugging experience. Label conflicts should surface as warnings.
