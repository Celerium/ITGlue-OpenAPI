"""Turn parsed documentation into an OpenAPI 3 document."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .constants import CONTENT_TYPE, OPENAPI_VERSION, PRODUCT_VERSION_KEY, REPOSITORY_URL, SOURCE_URL
from .parser import PATH_PARAMETER_PATTERN, Documentation, Param, Route, Section

METHOD_ORDER = ("get", "post", "put", "patch", "delete")
BODY_METHODS = frozenset({"post", "put", "patch", "delete"})
ACTION_NAMES = {"index": "list", "show": "get", "destroy": "delete", "bulk_destroy": "bulk_delete"}

DESCRIPTION = f"""\
Unofficial, best-effort OpenAPI specification generated from the official IT Glue developer documentation. \
It is not published or endorsed by IT Glue or Kaseya.

- Documentation: {SOURCE_URL}
- Pagination: https://help.itglue.kaseya.com/help/Content/1-admin/it-glue-api/pagination-in-the-it-glue-api.html
- Sorting and filtering: https://help.itglue.kaseya.com/help/Content/1-admin/it-glue-api/sorting-and-filtering-in-the-it-glue-api.html
- Generator and change history: {REPOSITORY_URL}

Requests authenticate with the `x-api-key` header. Payloads use `Content-Type: {CONTENT_TYPE}`.

The version of this document follows the IT Glue product version (see the release notes). When the API \
changes without a product version change, the current date (`YYYYMMDD`) is appended."""


def camel(value: str) -> str:
    first, *rest = [part for part in re.split(r"[_\W]+", value) if part]
    return first.lower() + "".join(part.capitalize() for part in rest)


def pascal(value: str) -> str:
    return "".join(part.capitalize() for part in re.split(r"[_\W]+", value) if part)


def to_openapi_path(path: str) -> str:
    return PATH_PARAMETER_PATTERN.sub(r"{\1}", path)


def path_parameters(path: str) -> list[str]:
    return PATH_PARAMETER_PATTERN.findall(path)


def with_nullable(schema: dict, nullable: bool) -> dict:
    return {**schema, "nullable": True} if nullable else dict(schema)


@dataclass
class BodyNode:
    param: Param | None = None
    children: dict[str, BodyNode] = field(default_factory=dict)
    items: BodyNode | None = None
    required: bool = False

    def child(self, token: str) -> BodyNode:
        if token == "_":
            if self.items is None:
                self.items = BodyNode()
            return self.items
        return self.children.setdefault(token, BodyNode())

    def to_schema(self) -> dict:
        schema: dict = {}
        if self.param is not None:
            schema = with_nullable(self.param.schema, self.param.nullable)
            if self.param.description:
                schema["description"] = self.param.description
        if self.items is not None:
            schema["type"] = "array"
            schema["items"] = self.items.to_schema()
        elif schema.get("type") == "array":
            schema.setdefault("items", {})
        if self.children:
            schema["type"] = "object"
            schema["properties"] = {name: node.to_schema() for name, node in self.children.items()}
            required = [name for name, node in self.children.items() if node.required]
            if required:
                schema["required"] = required
        elif not schema:
            schema["type"] = "object"
        return schema


def build_request_body(params: list[Param]) -> dict | None:
    body_params = [param for param in params if param.location == "body"]
    if not body_params:
        return None

    root = BodyNode()
    for param in body_params:
        tokens = re.findall(r"[^\[\]]+", param.name)
        if tokens and tokens[0] != "data":
            tokens.insert(0, "data")
        node = root
        for token in tokens:
            node = node.child(token)
        if node.param is None:
            node.param = param
            node.required = param.required

    data = root.children["data"]
    required = data.required if data.param else any(child.required for child in data.children.values())
    return {
        "required": required,
        "content": {
            CONTENT_TYPE: {
                "schema": {"type": "object", "properties": {"data": data.to_schema()}, "required": ["data"]}
            }
        },
    }


def build_parameters(params: list[Param], route: Route, route_paths: list[str]) -> list[dict]:
    in_path = set(path_parameters(route.path))
    in_other_routes = {name for path in route_paths for name in path_parameters(path)} - in_path
    documented = {param.name: param for param in params}
    query_names = [param.name for param in params if param.location in ("query", "url")]

    result: dict[tuple[str, str], dict] = {}
    for param in params:
        if param.location == "body":
            continue
        if param.name in in_path:
            location = "path"
        elif param.location == "url" and param.name in in_other_routes:
            continue
        else:
            location = "query"
        # `filter` / `page` hashes are redundant once their `filter[id]` style children exist.
        if (
            location == "query"
            and param.schema.get("type") == "object"
            and any(other.startswith(f"{param.name}[") for other in query_names)
        ):
            continue

        key = (location, param.name)
        entry = {
            "name": param.name,
            "in": location,
            "required": location == "path" or param.required,
            "schema": with_nullable(param.schema, param.nullable),
        }
        if param.description:
            entry["description"] = param.description
        if key in result:
            result[key]["required"] = result[key]["required"] or entry["required"]
            if "description" in entry:
                result[key].setdefault("description", entry["description"])
            continue
        result[key] = entry

    for name in path_parameters(route.path):
        if ("path", name) not in result:
            documented_param = documented.get(name)
            schema = dict(documented_param.schema) if documented_param else {"type": "string"}
            result[("path", name)] = {"name": name, "in": "path", "required": True, "schema": schema}

    order = {"path": 0, "query": 1}
    return [result[key] for key in sorted(result, key=lambda k: (order[k[0]], k[1]))]


def build_operation_id(section: Section, route_index: int, route: Route, taken: set[str]) -> str:
    resource, _, action = section.key.rpartition("__")
    resource = re.sub(r"^apiv1", "", resource)
    base = camel(ACTION_NAMES.get(action, action)) + pascal(resource)

    if route_index > 0:
        segments = [s for s in route.path.strip("/").split("/") if not s.startswith(":")]
        parents = (
            segments[: segments.index("relationships")] if "relationships" in segments else segments[:-1]
        )
        if parents:
            base += "For" + "".join(pascal(part) for part in parents)

    candidate, counter = base, 2
    while candidate in taken:
        candidate = f"{base}{counter}"
        counter += 1
    taken.add(candidate)
    return candidate


def build_responses(section: Section) -> dict:
    responses: dict[str, Any] = {
        "200": {
            "description": "Successful response",
            "content": {CONTENT_TYPE: {"schema": {"type": "object"}}},
        }
    }
    for code in sorted(section.errors):
        responses[code] = {"description": section.errors[code]}
    return responses


def build_spec(documentation: Documentation, product_version: str, version: str = "") -> dict[str, Any]:
    """Build the OpenAPI document. `version` is filled in later once change detection has run."""
    paths: dict[str, dict[str, Any]] = {}
    used_groups: set[str] = set()
    taken_ids: set[str] = set()

    for section in documentation.sections:
        group = documentation.groups.get(section.group_key)
        tag = group.name if group else pascal(re.sub(r"^apiv1", "", section.group_key)) or "General"
        route_paths = [route.path for route in section.routes]
        for index, route in enumerate(section.routes):
            path = to_openapi_path(route.path)
            if route.method in paths.get(path, {}):
                continue
            operation: dict[str, Any] = {
                "operationId": build_operation_id(section, index, route, taken_ids),
                "summary": route.summary or f"{route.method.upper()} {path}",
                "tags": [tag],
            }
            if section.description:
                operation["description"] = section.description
            operation["parameters"] = build_parameters(section.params, route, route_paths)
            body = build_request_body(section.params) if route.method in BODY_METHODS else None
            if body:
                operation["requestBody"] = body
            operation["responses"] = build_responses(section)
            paths.setdefault(path, {})[route.method] = operation
            used_groups.add(tag)

    if not paths:
        raise ValueError("No API operations were extracted; refusing to emit an empty specification.")

    ordered_paths = {
        path: {method: paths[path][method] for method in METHOD_ORDER if method in paths[path]}
        for path in sorted(paths)
    }
    descriptions = {group.name: group.description for group in documentation.groups.values()}
    tags = [
        {"name": name, **({"description": descriptions[name]} if descriptions.get(name) else {})}
        for name in sorted(used_groups)
    ]

    return {
        "openapi": OPENAPI_VERSION,
        "info": {
            "title": "IT Glue API",
            "version": version,
            PRODUCT_VERSION_KEY: product_version,
            "description": DESCRIPTION,
        },
        "externalDocs": {"description": "Official IT Glue API documentation", "url": SOURCE_URL},
        "servers": [
            {"url": "https://api.itglue.com", "description": "Default API server"},
            {"url": "https://api.eu.itglue.com", "description": "EU data center"},
            {"url": "https://api.au.itglue.com", "description": "Australia data center"},
        ],
        "tags": tags,
        "paths": ordered_paths,
        "components": {
            "securitySchemes": {"apiKeyAuth": {"type": "apiKey", "in": "header", "name": "x-api-key"}}
        },
        "security": [{"apiKeyAuth": []}],
    }
