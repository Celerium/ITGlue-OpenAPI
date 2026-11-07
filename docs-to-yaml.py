"""Generate an OpenAPI document from the IT Glue developer documentation."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup, Tag


SOURCE_URL = "https://api.itglue.com/developer/"
DEFAULT_OUTPUT = Path("ITGlue.yaml")
ENDPOINT_PATTERN = re.compile(r"^(GET|POST|PATCH|DELETE|PUT)\s+(\S+)$", re.IGNORECASE)
PATH_PARAMETER_PATTERN = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def clean_text(element: Tag | None) -> str:
    if element is None:
        return ""
    return re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()


def parameter_type(validation_text: str) -> dict[str, Any]:
    text = validation_text.lower()
    if ("true" in text and "false" in text) or "boolean" in text:
        return {"type": "boolean"}
    if "must be a number" in text or "must be an integer" in text:
        return {"type": "integer"}
    if "must be a hash" in text:
        return {"type": "object"}
    if "must be an array" in text or "must be a list" in text:
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "string"}


def add_parameter(parameters: list[dict[str, Any]], parameter: dict[str, Any]) -> None:
    for existing in parameters:
        if existing["name"] == parameter["name"] and existing["in"] == parameter["in"]:
            if parameter.get("description"):
                existing["description"] = parameter["description"]
            existing["required"] = existing["required"] or parameter["required"]
            if parameter.get("schema", {}).get("type") != "string":
                existing["schema"] = parameter["schema"]
            return
    parameters.append(parameter)


def extract_parameters(
    article: Tag, path_parameters: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    parameters: list[dict[str, Any]] = []
    request_body: dict[str, Any] | None = None
    params_heading = next(
        (heading for heading in article.find_all(["h2", "h3"]) if clean_text(heading).lower() == "params"),
        None,
    )
    params_table = params_heading.find_next("table") if params_heading else None

    if params_table:
        for row in params_table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 2:
                continue

            name_element = cells[0].find("strong")
            name = clean_text(name_element) or clean_text(cells[0]).split(" ", 1)[0]
            if not name:
                continue

            metadata = clean_text(cells[0].find("small"))
            description = clean_text(cells[1])
            required = "required" in metadata.lower()
            is_body_parameter = "param type: json body param" in description.lower()
            if name.startswith("data[") and request_body is not None:
                continue
            if is_body_parameter or name.startswith("data["):
                body_type = parameter_type(description).get("type")
                data_schema = (
                    {"type": "array", "items": {"type": "object"}}
                    if body_type == "array"
                    else {"type": "object"}
                )
                request_body = {
                    "required": required,
                    "content": {
                        "application/vnd.api+json": {
                            "schema": {
                                "type": "object",
                                "properties": {"data": data_schema},
                                "required": ["data"],
                            }
                        }
                    },
                }
                continue

            location = "path" if name in path_parameters else "query"
            parameter = {
                "name": name,
                "in": location,
                "description": description,
                "required": location == "path" or required,
                "schema": parameter_type(description),
            }
            add_parameter(parameters, parameter)

    for name in path_parameters:
        add_parameter(
            parameters,
            {
                "name": name,
                "in": "path",
                "description": "",
                "required": True,
                "schema": {"type": "string"},
            },
        )

    return parameters, request_body


def extract_errors(article: Tag) -> dict[str, dict[str, str]]:
    errors_heading = next(
        (heading for heading in article.find_all(["h2", "h3"]) if clean_text(heading).lower() == "errors"),
        None,
    )
    errors_table = errors_heading.find_next("table") if errors_heading else None
    responses: dict[str, dict[str, str]] = {}
    if errors_table:
        for row in errors_table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) >= 2:
                code = clean_text(cells[0])
                description = clean_text(cells[1])
                if re.fullmatch(r"[1-5]\d\d", code):
                    responses[code] = {"description": description or "Error response"}
    return responses


def build_openapi_spec(html: str, generated_on: date | None = None) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    spec: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {
            "title": "IT Glue API",
            "version": f"1.0.0.{(generated_on or datetime.now(timezone.utc).date()).strftime('%Y%m%d')}",
            "description": (
                "Generated from the official IT Glue developer documentation. This is a best-effort, "
                "unofficial specification and is not an IT Glue or Kaseya document.\n\n"
                "Documentation: https://api.itglue.com/developer/\n"
                "Pagination: https://help.itglue.kaseya.com/help/Content/1-admin/it-glue-api/"
                "pagination-in-the-it-glue-api.html\n"
                "Sorting and filtering: https://help.itglue.kaseya.com/help/Content/1-admin/it-glue-api/"
                "sorting-and-filtering-in-the-it-glue-api.html\n\n"
                "Requests use the x-api-key header. Payloads use Content-Type: "
                "application/vnd.api+json."
            ),
        },
        "servers": [
            {"url": "https://api.itglue.com", "description": "Default API server"},
            {"url": "https://api.eu.itglue.com", "description": "EU data center"},
            {"url": "https://api.au.itglue.com", "description": "Australia data center"},
        ],
        "paths": {},
        "components": {
            "securitySchemes": {
                "apiKeyAuth": {"type": "apiKey", "in": "header", "name": "x-api-key"}
            }
        },
        "security": [{"apiKeyAuth": []}],
    }

    ignored_classes = {"page__info", "page__apiv1flexible_asset_fields"}
    sections = soup.find_all("div", class_=re.compile(r"^page__"))
    for section in sections:
        classes = set(section.get("class", []))
        if classes & ignored_classes or "sidenav" in classes:
            continue

        heading = section.find("h1")
        match = ENDPOINT_PATTERN.match(clean_text(heading))
        if not match:
            continue

        method, documented_path = match.groups()
        method = method.lower()
        path_parameters = PATH_PARAMETER_PATTERN.findall(documented_path)
        path = PATH_PARAMETER_PATTERN.sub(r"{\1}", documented_path)
        article = section.find("article")
        if article is None:
            continue

        operation = spec["paths"].setdefault(path, {}).setdefault(
            method,
            {
                "summary": f"{method.upper()} {path}",
                "description": "",
                "parameters": [],
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/vnd.api+json": {"schema": {"type": "object"}}
                        },
                    }
                },
            },
        )

        description = clean_text(article.find("p"))
        if description:
            operation["description"] = description
        parameters, request_body = extract_parameters(article, path_parameters)
        for parameter in parameters:
            add_parameter(operation["parameters"], parameter)
        if request_body:
            operation["requestBody"] = request_body
        operation["responses"].update(extract_errors(article))

    if not spec["paths"]:
        raise ValueError("No API operations were extracted; refusing to emit an empty specification.")

    spec["paths"] = dict(sorted(spec["paths"].items()))
    for operations in spec["paths"].values():
        for operation in operations.values():
            operation["parameters"].sort(key=lambda parameter: (parameter["in"], parameter["name"]))
    return spec


def fetch_documentation(source_url: str = SOURCE_URL) -> str:
    response = requests.get(
        source_url,
        headers={"User-Agent": "ITGlue-OpenAPI-generator/1.0"},
        timeout=(10, 60),
    )
    response.raise_for_status()
    if "charset=" not in response.headers.get("Content-Type", "").lower():
        response.encoding = response.apparent_encoding or response.encoding
    return response.text


def write_spec(spec: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=100)
    validated = yaml.safe_load(serialized)
    if not isinstance(validated, dict) or not validated.get("paths"):
        raise ValueError("Generated YAML is invalid or contains no API paths.")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent, delete=False
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(output_path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-url", default=SOURCE_URL, help="IT Glue documentation URL")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output OpenAPI YAML path")
    args = parser.parse_args(argv)

    try:
        spec = build_openapi_spec(fetch_documentation(args.source_url))
        write_spec(spec, args.output)
    except (requests.RequestException, ValueError, yaml.YAMLError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(spec['paths'])} API paths to {args.output} (version {spec['info']['version']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())