"""`freellm` CLI — doctor, models, route, health commands."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from app.core.config import get_config, load_config
from app.core.registry import get_registry, load_registry
from app.core.router import resolve_candidates, resolve_for_physical_model


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="freellm",
        description="CLI for free-llm-hub — inspect routing, keys, and health.",
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("doctor", help="Verify configured keys against providers")
    sub.add_parser("models", help="List logical and physical models")

    p_route = sub.add_parser("route", help="Dry-run the router for a logical model")
    p_route.add_argument("model", nargs="?", default="auto", help="logical model name")
    p_route.add_argument("--prompt", default="hello", help="prompt to evaluate")
    p_route.add_argument("--json", action="store_true", help="emit JSON output")

    p_health = sub.add_parser("health", help="Print live health snapshot from /admin/health")
    p_health.add_argument("--url", default="http://localhost:8000", help="hub base URL")
    p_health.add_argument("--json", action="store_true", help="emit JSON output")
    p_health.add_argument("--probe", action="store_true", help="trigger /admin/probe first")

    args = parser.parse_args()
    if args.cmd is None:
        parser.print_help()
        return 0

    if args.cmd == "doctor":
        return asyncio.run(_doctor())
    if args.cmd == "models":
        return _models()
    if args.cmd == "route":
        return _route(args.model, args.prompt, json_output=args.json)
    if args.cmd == "health":
        return _health(args.url, probe=args.probe, json_output=args.json)
    parser.print_help()
    return 1


async def _doctor() -> int:
    load_config()
    load_registry()
    cfg = get_config()

    if not cfg.keys:
        print("No keys configured in config.yaml")
        return 1

    print(f"Checking {len(cfg.keys)} configured key(s)...\n")

    import importlib.util
    if importlib.util.find_spec("litellm") is None:
        print("litellm not installed. Run: pip install litellm")
        return 1

    results: list[tuple[str, str, str, float | None]] = []

    for kc in cfg.keys:
        if not kc.enabled:
            results.append((kc.label, kc.provider, "DISABLED", None))
            continue

        candidates = resolve_for_physical_model(
            _get_first_model_for_provider(kc.provider), cfg
        )
        candidate = next((c for c in candidates if c.key_label == kc.label), None)
        if candidate is None:
            results.append((kc.label, kc.provider, "NO MODEL IN REGISTRY", None))
            continue

        from app.providers.litellm_provider import call_provider

        start = time.time()
        try:
            await call_provider(
                candidate,
                [{"role": "user", "content": "hi"}],
                stream=False,
                max_tokens=1,
            )
            latency = (time.time() - start) * 1000
            results.append((kc.label, kc.provider, "OK", latency))
        except Exception as e:
            latency = (time.time() - start) * 1000
            err_msg = str(e)[:60]
            results.append((kc.label, kc.provider, f"FAIL: {err_msg}", latency))

    print(f"{'Label':<25} {'Provider':<15} {'Status':<40} {'Latency':>8}")
    print("-" * 92)
    for label, provider, status, latency in results:
        lat_str = f"{latency:.0f}ms" if latency is not None else "-"
        print(f"{label:<25} {provider:<15} {status:<40} {lat_str:>8}")

    failures = sum(1 for _, _, s, _ in results if s.startswith("FAIL"))
    if failures:
        print(f"\n{failures} key(s) failed.")
        return 1
    print("\nAll keys OK.")
    return 0


def _models() -> int:
    load_config()
    load_registry()
    cfg = get_config()
    registry = get_registry()

    enabled_providers = {k.provider for k in cfg.keys if k.enabled}

    print("Logical models (from policies):")
    for name in cfg.policies:
        policy = cfg.policies[name]
        caps = ", ".join(policy.capabilities) if policy.capabilities else "any"
        print(f"  {name:<25} prefer={policy.prefer}  caps=[{caps}]")

    print("\nPhysical models (from registry, with configured keys):")
    for entry in registry:
        if entry.provider in enabled_providers:
            rl = entry.rate_limit
            limits = []
            if rl.rpm:
                limits.append(f"{rl.rpm} rpm")
            if rl.rpd:
                limits.append(f"{rl.rpd} rpd")
            if rl.tpm:
                limits.append(f"{rl.tpm} tpm")
            caps = ", ".join(entry.capabilities[:3])
            print(f"  {entry.model:<40} {entry.provider:<12} {' | '.join(limits):<25} [{caps}]")

    return 0


def _route(model: str, prompt: str, json_output: bool = False) -> int:
    load_config()
    load_registry()

    candidates = resolve_candidates(model)
    if not candidates:
        msg = f"No candidates found for model '{model}'. Check config.yaml."
        if json_output:
            print(json.dumps({"error": msg, "candidates": []}))
        else:
            print(msg)
        return 1

    if json_output:
        out = {
            "model": model,
            "prompt_preview": prompt[:80],
            "candidates": [
                {
                    "rank": i,
                    "provider": c.provider,
                    "model": c.model,
                    "key_label": c.key_label,
                    "context_window": c.context_window,
                    "rate_limit_rpm": c.rate_limit_rpm,
                    "rate_limit_rpd": c.rate_limit_rpd,
                    "rate_limit_tpm": c.rate_limit_tpm,
                    "rate_limit_tpd": c.rate_limit_tpd,
                }
                for i, c in enumerate(candidates, 1)
            ],
            "would_pick": {
                "provider": candidates[0].provider,
                "model": candidates[0].model,
                "key_label": candidates[0].key_label,
            },
        }
        print(json.dumps(out, indent=2))
        return 0

    print(f"Routing for model='{model}', prompt='{prompt[:50]}...'\n")
    print(
        f"{'#':<3} {'Provider':<12} {'Model':<40} {'Key':<20} "
        f"{'Ctx':>7} {'RPM':>5} {'RPD':>6}"
    )
    print("-" * 100)
    for i, c in enumerate(candidates, 1):
        rpm = str(c.rate_limit_rpm) if c.rate_limit_rpm else "-"
        rpd = str(c.rate_limit_rpd) if c.rate_limit_rpd else "-"
        ctx = f"{c.context_window // 1000}k" if c.context_window else "-"
        print(
            f"{i:<3} {c.provider:<12} {c.model:<40} {c.key_label:<20} "
            f"{ctx:>7} {rpm:>5} {rpd:>6}"
        )

    pick = candidates[0]
    print(
        f"\nScheduler would pick: #1 → {pick.provider}/{pick.model} "
        f"(key={pick.key_label}, ctx={pick.context_window})"
    )
    return 0


def _health(base_url: str, probe: bool = False, json_output: bool = False) -> int:
    try:
        import httpx
    except ImportError:
        print("httpx not installed. Run: pip install httpx")
        return 1

    base = base_url.rstrip("/")
    try:
        with httpx.Client(timeout=10.0) as client:
            if probe:
                client.post(f"{base}/admin/probe")
            r = client.get(f"{base}/admin/health")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"Failed to reach {base}/admin/health: {e}")
        return 1

    health = data.get("health", {})
    if json_output:
        print(json.dumps(data, indent=2))
        return 0

    if not health:
        print("No health entries (probe may not have run yet).")
        return 0

    print(f"{'Key':<28} {'Status':<10} {'Latency':>10} {'Failures':>9} {'Last error':<30}")
    print("-" * 92)
    any_down = False
    for key_id, st in health.items():
        status = st.get("status", "unknown")
        if status in ("down", "degraded"):
            any_down = True
        lat = st.get("last_latency_ms")
        lat_str = f"{lat:.0f}ms" if lat is not None else "-"
        fails = st.get("consecutive_failures", 0)
        err = (st.get("last_error") or "")[:28]
        print(f"{key_id:<28} {status:<10} {lat_str:>10} {fails:>9} {err:<30}")

    return 1 if any_down else 0


def _get_first_model_for_provider(provider: str) -> str:
    from app.core.registry import get_models_for_provider
    models = get_models_for_provider(provider)
    if models:
        return models[0].model
    return ""


if __name__ == "__main__":
    sys.exit(main())
