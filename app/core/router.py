"""Router — maps a logical model to an ordered list of (provider, model, key) candidates."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import HubConfig, KeyConfig, PolicyConfig, get_config
from app.core.registry import RegistryEntry, get_registry


@dataclass
class Candidate:
    provider: str
    model: str
    endpoint: str
    protocol: str
    auth_style: str
    key: str
    key_label: str
    context_window: int
    rate_limit_rpm: int | None = None
    rate_limit_rpd: int | None = None
    rate_limit_tpm: int | None = None
    rate_limit_tpd: int | None = None


def resolve_candidates(
    logical_model: str,
    config: HubConfig | None = None,
) -> list[Candidate]:
    cfg = config or get_config()
    registry = get_registry()
    policy = cfg.policies.get(logical_model, cfg.policies.get("auto", PolicyConfig()))

    enabled_keys = [k for k in cfg.keys if k.enabled]
    if not enabled_keys:
        return []

    key_by_provider: dict[str, list[KeyConfig]] = {}
    for k in enabled_keys:
        key_by_provider.setdefault(k.provider, []).append(k)

    filtered = _filter_by_capability(registry, policy)
    filtered = _filter_by_context(filtered, policy)
    filtered = _apply_prefer_avoid(filtered, policy)

    candidates: list[Candidate] = []
    for entry in filtered:
        keys = key_by_provider.get(entry.provider, [])
        for kc in keys:
            rl = entry.rate_limit
            if kc.override_limits:
                ol = kc.override_limits
                rpm = ol.rpm if ol.rpm is not None else rl.rpm
                rpd = ol.rpd if ol.rpd is not None else rl.rpd
                tpm = ol.tpm if ol.tpm is not None else rl.tpm
                tpd = ol.tpd if ol.tpd is not None else rl.tpd
            else:
                rpm, rpd, tpm, tpd = rl.rpm, rl.rpd, rl.tpm, rl.tpd

            candidates.append(
                Candidate(
                    provider=entry.provider,
                    model=entry.model,
                    endpoint=entry.endpoint,
                    protocol=entry.protocol,
                    auth_style=entry.auth_style,
                    key=kc.key.get_secret_value(),
                    key_label=kc.label,
                    context_window=entry.context_window,
                    rate_limit_rpm=rpm,
                    rate_limit_rpd=rpd,
                    rate_limit_tpm=tpm,
                    rate_limit_tpd=tpd,
                )
            )
    return candidates


def resolve_for_physical_model(model_name: str, config: HubConfig | None = None) -> list[Candidate]:
    cfg = config or get_config()
    registry = get_registry()
    entries = [e for e in registry if e.model == model_name]
    if not entries:
        return []

    enabled_keys = [k for k in cfg.keys if k.enabled]
    key_by_provider: dict[str, list[KeyConfig]] = {}
    for k in enabled_keys:
        key_by_provider.setdefault(k.provider, []).append(k)

    candidates: list[Candidate] = []
    for entry in entries:
        keys = key_by_provider.get(entry.provider, [])
        for kc in keys:
            rl = entry.rate_limit
            candidates.append(
                Candidate(
                    provider=entry.provider,
                    model=entry.model,
                    endpoint=entry.endpoint,
                    protocol=entry.protocol,
                    auth_style=entry.auth_style,
                    key=kc.key.get_secret_value(),
                    key_label=kc.label,
                    context_window=entry.context_window,
                    rate_limit_rpm=rl.rpm,
                    rate_limit_rpd=rl.rpd,
                    rate_limit_tpm=rl.tpm,
                    rate_limit_tpd=rl.tpd,
                )
            )
    return candidates


def _filter_by_capability(
    entries: list[RegistryEntry], policy: PolicyConfig
) -> list[RegistryEntry]:
    if not policy.capabilities:
        return entries
    required = set(policy.capabilities)
    return [e for e in entries if required.issubset(set(e.capabilities))]


def _filter_by_context(
    entries: list[RegistryEntry], policy: PolicyConfig
) -> list[RegistryEntry]:
    if policy.min_context is None:
        return entries
    return [e for e in entries if e.context_window >= policy.min_context]


def _apply_prefer_avoid(
    entries: list[RegistryEntry], policy: PolicyConfig
) -> list[RegistryEntry]:
    if policy.avoid:
        entries = [e for e in entries if e.provider not in policy.avoid]

    if not policy.prefer:
        return entries

    prefer_order = {p: i for i, p in enumerate(policy.prefer)}
    max_idx = len(policy.prefer)

    def sort_key(e: RegistryEntry) -> int:
        return prefer_order.get(e.provider, max_idx)

    return sorted(entries, key=sort_key)
