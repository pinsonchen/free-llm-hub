# Technical Design — free-llm-hub

Status: **Draft v0.1** · Owner: @pinsonchen · Last updated: 2026-05-27

## 1. Problem & Scope

### 1.1 Problem statement
Developers building hobby projects, internal tooling, or low-traffic agents want to combine many free-tier LLM APIs (Groq, Gemini, SiliconFlow, Cerebras, Zhipu, DeepSeek, OpenRouter `:free`, etc.) without:

- Writing N SDK adapters
- Manually tracking which key still has quota today
- Hand-coding retry / fallback when one provider rate-limits
- Re-learning each provider's rate-limit policy every month

### 1.2 In scope (MVP)
- Single OpenAI-compatible gateway (`/v1/chat/completions`, `/v1/models`, streaming)
- User-supplied multi-key, multi-provider configuration
- Per-key + per-model **quota tracker** with sliding window
- Health probing and exponential cooldown on errors / 429
- Community-maintained YAML **registry** of free tiers
- CLI to inspect quota, health, and effective routing decisions

### 1.3 Out of scope
- Account creation automation, shared key pools, captcha solving — **explicit non-goals** (ToS risk).
- Billing, accounting, user management, marketplace features — covered by `one-api` / `new-api`.
- Fine-tuning, embedding caches, vector DBs — possible future plugins, not core.
- Training-data collection or telemetry that leaves the user's machine.

## 2. Prior Art & Differentiation

| Project | What it does well | Gap we address |
|---|---|---|
| **LiteLLM** | 100+ provider adapters, proxy mode, load balancing | No free-tier registry, no quota-aware routing, requires manual model lists |
| **one-api / new-api** | Production-grade key distribution + billing | Optimized for commercial reselling; heavyweight; not "free-tier first" |
| **OpenRouter** | Hosted aggregator with `:free` models | Closed source; only their roster; can't bring your own Groq key |
| **LLM-API-Key-Proxy** | Key rotation + cooldowns | Single-user, no registry, no smart routing by task |
| **free-llm-collect / awesome-free-llm** | Curated registries | Just lists — no runtime, no enforcement |

**Differentiator:** we are the only project that combines a **community-curated free-tier registry** with a **runtime that respects those limits**, behind a familiar OpenAI surface. We deliberately stay user-owned-keys-only to avoid the ToS swamp.

## 3. High-level Architecture

```
                   ┌──────────────────────────────────────┐
   OpenAI SDK ──▶  │  FastAPI Gateway  (/v1/*)            │
   curl       ──▶  │  - auth (local key)                  │
                   │  - request normalization             │
                   └────────────────┬─────────────────────┘
                                    ▼
                   ┌──────────────────────────────────────┐
                   │  Router                              │
                   │  logical model  →  candidate list    │
                   │  (cap, lang, speed, task tags)       │
                   └────────────────┬─────────────────────┘
                                    ▼
                   ┌──────────────────────────────────────┐
                   │  Scheduler                           │
                   │  pick first candidate where          │
                   │    quota.ok AND health.ok            │
                   │  emit "decision" event for tracing   │
                   └────────────────┬─────────────────────┘
                                    ▼
                   ┌──────────────────────────────────────┐
                   │  Provider Call (LiteLLM)             │
                   │  - inject API key                    │
                   │  - stream / non-stream                │
                   │  - parse usage + ratelimit headers   │
                   └────────────────┬─────────────────────┘
                       ┌────────────┴────────────┐
                       ▼                         ▼
                ┌──────────────┐         ┌──────────────┐
                │ QuotaTracker │         │ HealthProbe  │
                │ Redis|SQLite │         │ cooldown LRU │
                └──────────────┘         └──────────────┘

           Registry (registry/*.yaml) ── loaded at boot, hot-reloadable
```

## 4. Components

### 4.1 Registry
- Source of truth: `registry/<provider>.yaml`, validated by a JSON Schema in `registry/schema.json`.
- Each entry records: `provider`, `model`, `endpoint`, `protocol` (`openai|anthropic|gemini`), `auth_style`, `rate_limit` (`rpm`, `rpd`, `tpm`, `tpd`), `context_window`, `capabilities` (`coding`, `chinese`, `long_context`, `vision`, `tools`), `notes`, `last_verified`.
- The registry is **data, not code** — community PRs are encouraged. CI validates schema and required fields. Maintainers periodically run a "verify" job that probes endpoints.

### 4.2 Configuration
- `config.yaml` (user-owned, gitignored) declares:
  - `keys`: a list of `{provider, key, label, enabled, override_limits?}`
  - `policies`: per-logical-model routing preference (`prefer`, `avoid`, `min_context`, `max_latency_ms`)
  - `storage`: `sqlite:///./hub.db` (default) or `redis://...`
  - `auth`: local API key required from clients
- Schema validated with Pydantic at startup; bad config fails fast with a friendly diff.

### 4.3 Router
- Input: incoming request (logical model, prompt features).
- Output: ordered list of candidates `[(provider, model, key, score), ...]`.
- Scoring inputs:
  1. Capability match against the registry (hard filter)
  2. User policy (prefer/avoid)
  3. Estimated remaining quota (soft; from QuotaTracker)
  4. Recent latency / error rate (soft; from HealthProbe)
- A logical model `auto` defaults to: "cheapest-free that satisfies capability with non-empty quota".

### 4.4 Scheduler
- Walks the candidate list and picks the first `quota.ok AND health.ok`.
- On call success: increments quota counters using actual `usage.total_tokens`; clears any error backoff for that key.
- On 429 / 5xx: applies escalating cooldown (10s → 30s → 60s → 120s → cap 5m); demotes candidate; retries next.
- Emits an internal `decision` event (structured JSON log) for observability.

### 4.5 QuotaTracker
- Sliding-window counter keyed by `(provider, key_hash, model, window)`.
- Windows: `1m` (RPM/TPM), `1d` (RPD/TPD).
- Storage backends:
  - **SQLite** (default, zero-dep): table + periodic compaction
  - **Redis** (optional, multi-process): `INCRBY` + `EXPIRE`, or `ZADD` + range queries
- Limits sourced from registry, overridable per-key in config.
- Conservative: if a provider returns `x-ratelimit-remaining`, prefer that over our counter.

### 4.6 HealthProbe
- Lightweight background task: every N minutes, send a 1-token "ping" prompt to a small subset of `(provider, key)` pairs to detect silent revocation / region blocks.
- Marks failing pairs as `cooldown_until = now + backoff`.
- Cheap and rate-limited (probes count against the same QuotaTracker).

### 4.7 Provider adapters
- Default to **LiteLLM** for 100+ providers (huge time saving).
- For providers LiteLLM doesn't cover well (e.g. niche Chinese ones), provide a thin `Provider` ABC with `chat_completions(req) -> stream`.
- All adapters must:
  - Pass through OpenAI-style messages, tools, response_format
  - Surface `usage` and any `x-ratelimit-*` headers back to the Scheduler
  - Translate provider errors into a small canonical set (`RateLimited`, `Unauthorized`, `ProviderDown`, `BadRequest`)

### 4.8 API surface
- `POST /v1/chat/completions` — streaming + non-streaming
- `GET  /v1/models` — union of enabled models (logical + physical)
- `GET  /admin/quota` — per-key remaining (auth-gated)
- `GET  /admin/health` — per-key probe state
- `POST /admin/reload` — reload config + registry
- (Future) `GET /admin/decisions?trace=<id>` — explain a routing decision

### 4.9 CLI (`freellm`)
- `freellm doctor` — verify each configured key against its provider, print quota & latency
- `freellm models` — list logical + physical models with scores
- `freellm route "<prompt>"` — dry-run the router, print the would-be decision
- `freellm registry verify` — re-probe registry endpoints (maintainer use)

## 5. Data Model

```python
# pydantic sketches
class RegistryEntry(BaseModel):
    provider: str
    model: str
    endpoint: HttpUrl
    protocol: Literal["openai", "anthropic", "gemini"]
    auth_style: Literal["bearer", "x-api-key", "query"]
    rate_limit: RateLimit  # rpm / rpd / tpm / tpd, all optional
    context_window: int
    capabilities: set[Capability]
    notes: str | None
    last_verified: date

class KeyConfig(BaseModel):
    provider: str
    key: SecretStr
    label: str
    enabled: bool = True
    override_limits: RateLimit | None = None

class QuotaState(BaseModel):
    key_hash: str
    model: str
    window: Literal["1m", "1d"]
    used: int
    limit: int
    resets_at: datetime
```

## 6. Failure & Edge Cases

| Scenario | Behavior |
|---|---|
| All candidates exhausted | 429 to client with `Retry-After` = soonest reset; structured error body lists what was tried |
| Provider returns valid 200 but body is HTML / captcha | Detected, treated as `ProviderDown`, cooldown 5m, alerts in logs |
| Streaming connection drops mid-response | Token usage accounted up to last delta; counters incremented conservatively |
| Clock skew between hub & provider | We trust `x-ratelimit-reset` when present, otherwise use local clock |
| Config reload mid-flight | Atomic swap; in-flight requests use old config until completion |
| Registry corrupted PR | CI schema check blocks merge; runtime falls back to last good cached registry |

## 7. Security

- Local API key required for all `/v1/*` and `/admin/*` calls (defaults to a randomly generated value printed on first run).
- Provider keys stored only in `config.yaml` (gitignored) and held as `SecretStr` in memory; never logged, never echoed in admin endpoints (only last 4 chars).
- No outbound telemetry. Optional opt-in anonymous usage report (off by default).
- Admin endpoints disabled when bound to non-loopback unless `auth.admin_token` is set.

## 8. Observability

- Structured JSON logs (`request_id`, `decision`, `provider`, `model`, `key_label`, `latency_ms`, `usage`, `outcome`)
- `/metrics` Prometheus endpoint: `freellm_requests_total{provider,model,outcome}`, `freellm_tokens_total`, `freellm_quota_remaining`, `freellm_cooldown_seconds`
- `freellm route` CLI for human-readable explain

## 9. Deployment

- Single-binary-feel via `uvicorn app.main:app`
- Docker image (slim Python 3.12)
- `docker-compose.yml` includes optional Redis
- Cloudflare Workers / Vercel: deferred — Python + Redis assumptions don't map cleanly. A Node/Hono port is a possible v2.

## 10. Risks

| Risk | Mitigation |
|---|---|
| **ToS gray area** if users abuse multi-account | Strong README disclaimer; refuse to ship any "auto-register" feature; reject PRs that add captcha bypass |
| Registry rot (free tiers change) | Schema requires `last_verified`; CI flags entries older than 90 days; community PR culture |
| Provider blocks our default User-Agent | Configurable UA; default to a neutral string |
| LiteLLM API drift | Pin a known-good version; integration tests against a local mock |
| Quota overshoot at low concurrency boundary | Soft buffer (e.g. reserve 10% headroom) configurable per key |

## 11. Open Questions

1. Do we want a hosted demo (with the maintainers' own keys for a few free tiers) or strictly self-hosted? Hosted adds support burden + ToS exposure.
2. Should we ship an experimental "quality-aware" router that benchmarks providers on user prompts? (Possibly a v2 plugin to keep MVP focused.)
3. How aggressive should the auto-fallback be by default? (Proposed: at most 3 retries across providers per request.)
4. Should the registry live in this repo or a sibling repo `free-llm-hub-registry`? (Tentatively here, to keep schema + data co-located until contributor volume justifies splitting.)
