"""`freellm` CLI — doctor, models, route commands."""

from __future__ import annotations

import asyncio
import sys
import time

from app.core.config import get_config, load_config
from app.core.registry import get_registry, load_registry
from app.core.router import resolve_candidates, resolve_for_physical_model


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        _print_help()
        return 0

    cmd = args[0]
    if cmd == "doctor":
        return asyncio.run(_doctor())
    elif cmd == "models":
        return _models()
    elif cmd == "route":
        prompt = args[1] if len(args) > 1 else "hello"
        return _route(prompt)
    else:
        print(f"Unknown command: {cmd}")
        _print_help()
        return 1


def _print_help() -> None:
    print("""freellm — CLI for free-llm-hub

Commands:
  doctor    Verify configured keys against providers (latency + status)
  models    List available logical + physical models
  route     Dry-run the router for a given prompt/model
""")


async def _doctor() -> int:
    load_config()
    load_registry()
    cfg = get_config()

    if not cfg.keys:
        print("No keys configured in config.yaml")
        return 1

    print(f"Checking {len(cfg.keys)} configured key(s)...\n")

    try:
        import importlib.util
        if importlib.util.find_spec("litellm") is None:
            raise ImportError
    except ImportError:
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


def _route(prompt: str) -> int:
    load_config()
    load_registry()

    candidates = resolve_candidates("auto")
    if not candidates:
        print("No candidates found for model 'auto'. Check config.yaml.")
        return 1

    print(f"Routing for model='auto', prompt='{prompt[:50]}...'\n")
    print(f"{'#':<3} {'Provider':<12} {'Model':<40} {'Key':<20} {'RPM':>5} {'RPD':>6}")
    print("-" * 90)
    for i, c in enumerate(candidates, 1):
        rpm = str(c.rate_limit_rpm) if c.rate_limit_rpm else "-"
        rpd = str(c.rate_limit_rpd) if c.rate_limit_rpd else "-"
        print(f"{i:<3} {c.provider:<12} {c.model:<40} {c.key_label:<20} {rpm:>5} {rpd:>6}")

    print(f"\nScheduler would pick: #{1} (first available)")
    return 0


def _get_first_model_for_provider(provider: str) -> str:
    from app.core.registry import get_models_for_provider
    models = get_models_for_provider(provider)
    if models:
        return models[0].model
    return ""


if __name__ == "__main__":
    sys.exit(main())
