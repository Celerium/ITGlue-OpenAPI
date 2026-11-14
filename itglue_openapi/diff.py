"""Describe what changed between two generated specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .constants import PRODUCT_VERSION_KEY

METHODS = ("get", "post", "put", "patch", "delete")
VOLATILE_INFO_KEYS = ("version", PRODUCT_VERSION_KEY)
MAX_RELEASE_NOTES_CHARS = 60_000


@dataclass
class SpecDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, list[str]] = field(default_factory=dict)
    other: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed or self.other)

    def summary(self) -> str:
        return f"{len(self.added)} added, {len(self.removed)} removed, {len(self.changed)} modified"


def comparable(spec: dict[str, Any]) -> dict[str, Any]:
    """The part of a spec that counts as an API change (version bookkeeping is excluded)."""
    info = {k: v for k, v in spec.get("info", {}).items() if k not in VOLATILE_INFO_KEYS}
    return {**spec, "info": info}


def operations(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"{method.upper()} {path}": operation
        for path, item in spec.get("paths", {}).items()
        for method, operation in item.items()
        if method in METHODS
    }


def flatten_schema(schema: dict[str, Any], prefix: str = "") -> dict[str, dict[str, Any]]:
    """Map dotted property paths to the facts worth tracking (type, enum, required, nullable)."""
    flat: dict[str, dict[str, Any]] = {}
    required = set(schema.get("required", []))
    for name, child in schema.get("properties", {}).items():
        path = f"{prefix}.{name}" if prefix else name
        flat[path] = {
            "type": child.get("type"),
            "enum": child.get("enum"),
            "nullable": child.get("nullable", False),
            "required": name in required,
            "description": child.get("description"),
        }
        flat.update(flatten_schema(child, path))
    items = schema.get("items")
    if isinstance(items, dict):
        flat.update(flatten_schema(items, f"{prefix}[]"))
    return flat


def describe_change(label: str, old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    lines = []
    for key in ("type", "enum", "required", "nullable"):
        if old.get(key) != new.get(key):
            lines.append(f"{label}: {key} `{old.get(key)}` → `{new.get(key)}`")
    if old.get("description") != new.get("description"):
        lines.append(f"{label}: description changed")
    return lines


def parameter_facts(parameter: dict[str, Any]) -> dict[str, Any]:
    schema = parameter.get("schema", {})
    return {
        "type": schema.get("type"),
        "enum": schema.get("enum"),
        "required": parameter.get("required", False),
        "nullable": schema.get("nullable", False),
        "description": parameter.get("description"),
    }


def diff_operation(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    for key in ("summary", "description"):
        if old.get(key) != new.get(key):
            changes.append(f"{key} changed")

    old_params = {(p["in"], p["name"]): p for p in old.get("parameters", [])}
    new_params = {(p["in"], p["name"]): p for p in new.get("parameters", [])}
    for key in sorted(new_params.keys() - old_params.keys()):
        requirement = "required" if new_params[key].get("required") else "optional"
        changes.append(f"parameter added: `{key[1]}` ({key[0]}, {requirement})")
    for key in sorted(old_params.keys() - new_params.keys()):
        changes.append(f"parameter removed: `{key[1]}` ({key[0]})")
    for key in sorted(old_params.keys() & new_params.keys()):
        changes.extend(
            describe_change(
                f"parameter `{key[1]}` ({key[0]})",
                parameter_facts(old_params[key]),
                parameter_facts(new_params[key]),
            )
        )

    def body_schema(operation: dict[str, Any]) -> dict[str, Any]:
        content = operation.get("requestBody", {}).get("content", {})
        return next(iter(content.values()), {}).get("schema", {})

    old_body, new_body = flatten_schema(body_schema(old)), flatten_schema(body_schema(new))
    if "requestBody" in new and "requestBody" not in old:
        changes.append("request body added")
    elif "requestBody" in old and "requestBody" not in new:
        changes.append("request body removed")
    for key in sorted(new_body.keys() - old_body.keys()):
        requirement = "required" if new_body[key]["required"] else "optional"
        changes.append(f"body field added: `{key}` ({requirement})")
    for key in sorted(old_body.keys() - new_body.keys()):
        changes.append(f"body field removed: `{key}`")
    for key in sorted(old_body.keys() & new_body.keys()):
        changes.extend(describe_change(f"body field `{key}`", old_body[key], new_body[key]))

    old_responses, new_responses = old.get("responses", {}), new.get("responses", {})
    for code in sorted(new_responses.keys() - old_responses.keys()):
        changes.append(f"response added: `{code}` {new_responses[code].get('description', '')}".rstrip())
    for code in sorted(old_responses.keys() - new_responses.keys()):
        changes.append(f"response removed: `{code}`")

    if not changes and old != new:
        changes.append("definition changed")
    return changes


def diff_specs(old: dict[str, Any] | None, new: dict[str, Any]) -> SpecDiff:
    result = SpecDiff()
    old_ops = operations(old) if old else {}
    new_ops = operations(new)
    result.added = sorted(new_ops.keys() - old_ops.keys())
    result.removed = sorted(old_ops.keys() - new_ops.keys())
    for key in sorted(new_ops.keys() & old_ops.keys()):
        if old_ops[key] != new_ops[key]:
            result.changed[key] = diff_operation(old_ops[key], new_ops[key])

    if old:
        before, after = comparable(old), comparable(new)
        for key in sorted(before.keys() | after.keys()):
            if key != "paths" and before.get(key) != after.get(key):
                result.other.append(key)
    return result


def render_markdown(diff: SpecDiff, heading_level: int = 3) -> str:
    """Render a diff as markdown suitable for release notes and the changelog."""
    marker = "#" * heading_level
    lines: list[str] = []

    if diff.added:
        lines += [f"{marker} Added endpoints", *[f"- `{key}`" for key in diff.added], ""]
    if diff.removed:
        lines += [f"{marker} Removed endpoints", *[f"- `{key}`" for key in diff.removed], ""]
    if diff.changed:
        lines.append(f"{marker} Modified endpoints")
        for key, changes in diff.changed.items():
            lines.append(f"- `{key}`")
            lines.extend(f"  - {change}" for change in changes)
        lines.append("")
    if diff.other:
        lines += [
            f"{marker} Other changes",
            *[f"- `{key}` section of the spec changed" for key in diff.other],
            "",
        ]

    text = "\n".join(lines).strip()
    if len(text) > MAX_RELEASE_NOTES_CHARS:
        text = (
            text[:MAX_RELEASE_NOTES_CHARS].rsplit("\n", 1)[0]
            + "\n\n_Change list truncated; see the commit diff for the rest._"
        )
    return text
