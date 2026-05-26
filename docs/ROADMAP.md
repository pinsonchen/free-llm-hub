# Roadmap

## M0 — Design freeze (this PR)
- [x] README, TECH_DESIGN, ROADMAP, CONTRIBUTING
- [x] Registry schema (`registry/schema.json`)
- [x] Seed registry for 3 providers (Groq, Gemini, SiliconFlow)
- [x] Project skeleton (FastAPI app, package layout, pyproject)
- [x] CI: schema validation for `registry/*.yaml`

## M1 — Walking skeleton (target: 2 weeks)
- [ ] OpenAI-compatible `/v1/chat/completions` (non-streaming) backed by LiteLLM
- [ ] Config loader (`config.yaml` + Pydantic)
- [ ] Router with hard capability filter (no quota awareness yet)
- [ ] Round-robin scheduler across configured keys for one logical model
- [ ] `freellm doctor` smoke test
- [ ] Dockerfile + docker-compose (without Redis)
- [ ] Pytest + GitHub Actions test job

## M2 — Quota-aware routing
- [ ] QuotaTracker (SQLite backend)
- [ ] Parse `x-ratelimit-*` headers across providers
- [ ] Scheduler honors quota and cooldown
- [ ] `/admin/quota` endpoint + CLI `freellm models`
- [ ] Structured JSON logs with `decision` events

## M3 — Resilience
- [ ] HealthProbe background task
- [ ] Escalating cooldowns + circuit breaker
- [ ] Streaming `/v1/chat/completions`
- [ ] Redis backend for QuotaTracker (multi-process)
- [ ] Prometheus `/metrics`

## M4 — Quality of life
- [ ] Web admin UI (read-only: quota, decisions, health)
- [ ] `freellm route "<prompt>"` dry-run
- [ ] Hot reload of registry & config
- [ ] Expanded registry: Cerebras, OpenRouter, Zhipu, DeepSeek, Kimi, Cloudflare WAI

## v2 — Stretch
- [ ] Quality-aware routing (benchmark plugin)
- [ ] Node/Hono port for edge deployment
- [ ] Optional embedding/cache layer
