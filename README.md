# free-llm-hub

> Developer-first router for **free-tier LLM APIs**: unify, schedule, and squeeze every free token from Groq, Gemini, SiliconFlow, Cerebras, OpenRouter, Zhipu, DeepSeek and more — behind a single OpenAI-compatible endpoint.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-design--phase-orange.svg)](docs/TECH_DESIGN.md)

## Why

The free-tier LLM landscape is exploding (Gemini 2.5 Flash, Groq Llama 3.3 70B, SiliconFlow, Cerebras, OpenRouter `:free` models, Zhipu GLM-4.6, DeepSeek …). But every provider has different rate limits, different SDKs, different quota policies, and any of them can stop working at any time.

`free-llm-hub` is the **smart router** that:
- Aggregates **your own** free-tier API keys behind one OpenAI-compatible URL
- Tracks per-key / per-model quota in real time and routes to whatever still has budget
- Auto-fails-over when a provider rate-limits or goes down
- Ships a community-maintained **registry** of every known free tier and its limits

## Non-goals

- **We do not auto-register accounts.** You bring your own keys; we never share or pool them across users.
- **We do not bypass provider Terms of Service.** No proxy farms, no key scraping, no captcha solving.
- **We are not a billing/marketplace.** For commercial reselling, use `one-api` / `new-api`.

## Status

This repository is in the **design phase**. See [`docs/TECH_DESIGN.md`](docs/TECH_DESIGN.md) for the architecture and [`docs/ROADMAP.md`](docs/ROADMAP.md) for the milestone plan. The first executable MVP is targeted for **M1** (see roadmap).

## Quickstart (preview)

```bash
# clone & install
git clone https://github.com/pinsonchen/free-llm-hub.git
cd free-llm-hub
uv sync   # or: pip install -e .

# configure your free-tier keys
cp config.example.yaml config.yaml
$EDITOR config.yaml

# run the gateway
uvicorn app.main:app --reload --port 8787

# point any OpenAI client at it
curl http://localhost:8787/v1/chat/completions \
  -H "Authorization: Bearer local-anything" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"hi"}]}'
```

## Architecture (one-paragraph)

A FastAPI gateway exposes OpenAI-compatible `/v1/*` endpoints. Requests hit a **Router** that maps a logical model (e.g. `auto`, `coding-fast`, `chinese-long-context`) to a ranked list of physical `(provider, model, key)` candidates. The **Scheduler** picks the next viable candidate using a **QuotaTracker** (sliding window, Redis or SQLite) plus a **HealthProbe**-fed cooldown table. Provider calls go through **LiteLLM** so we get 100+ adapters for free. The candidate list itself is derived from a versioned **Registry** (`registry/*.yaml`) — the source of truth for every known free tier.

See [`docs/TECH_DESIGN.md`](docs/TECH_DESIGN.md) for the full design.

## Contributing

We especially want PRs against [`registry/`](registry/) when free-tier policies change. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT — see [`LICENSE`](LICENSE).
