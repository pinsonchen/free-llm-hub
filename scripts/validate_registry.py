"""Validate every YAML file in registry/ against registry/schema.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_DIR = ROOT / "registry"
SCHEMA_PATH = REGISTRY_DIR / "schema.json"


class _StringDateLoader(yaml.SafeLoader):
    """SafeLoader that keeps ISO dates as strings (schema expects type=string)."""


def _date_as_string(loader: yaml.Loader, node: yaml.Node) -> str:
    return loader.construct_scalar(node)


_StringDateLoader.add_constructor("tag:yaml.org,2002:timestamp", _date_as_string)


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    validator = Draft7Validator(schema)

    failures: list[str] = []
    files = sorted(p for p in REGISTRY_DIR.glob("*.yaml"))
    if not files:
        print("no registry files found", file=sys.stderr)
        return 1

    for path in files:
        docs = yaml.load(path.read_text(), Loader=_StringDateLoader) or []
        if not isinstance(docs, list):
            failures.append(f"{path.name}: top-level must be a list of entries")
            continue
        for i, entry in enumerate(docs):
            for err in validator.iter_errors(entry):
                loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
                failures.append(f"{path.name}[{i}] {loc}: {err.message}")

    if failures:
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        return 1

    print(f"OK — validated {len(files)} registry file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
