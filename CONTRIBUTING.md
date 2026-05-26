# Contributing to free-llm-hub

Thanks for helping! The single most valuable contribution right now is **keeping the registry accurate**.

## Updating the registry

Each provider lives in `registry/<provider>.yaml`. Entries must validate against `registry/schema.json` (CI enforces this).

Required fields:

- `provider`, `model`, `endpoint`, `protocol`, `auth_style`
- `rate_limit` — at least one of `rpm`, `rpd`, `tpm`, `tpd`
- `context_window`
- `capabilities` — any of `coding`, `chinese`, `english`, `long_context`, `vision`, `tools`, `json_mode`
- `last_verified` — `YYYY-MM-DD` when you personally tested or read official docs

Optional: `notes`, `signup_url`, `docs_url`.

**Please link the official rate-limit doc** in your PR description so reviewers can verify.

## Code contributions

- Python ≥ 3.11
- We use `uv` (or `pip`) + `ruff` + `pytest`
- Run `uv run ruff check . && uv run pytest -q` before pushing
- New providers go under `app/providers/` only when LiteLLM doesn't cover them well — otherwise just add to the registry

## Non-goals (please don't PR these)

- Account auto-registration, captcha solving, multi-account scripting
- Shared key pools across users
- Telemetry that leaves the user's machine without opt-in
- Anything that violates a provider's Terms of Service

If you're unsure whether something belongs, open an issue first.
