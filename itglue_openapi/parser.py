"""Parse the IT Glue developer documentation HTML into structured data."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

ROUTE_PATTERN = re.compile(r"^(GET|POST|PATCH|PUT|DELETE)\s+(/\S*)$", re.IGNORECASE)
PATH_PARAMETER_PATTERN = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
STATUS_CODE_PATTERN = re.compile(r"\b[1-5]\d\d\b")

# Rows documented without the JSON:API `data` wrapper (a quirk of some endpoints) still belong to the body.
BODY_ROOTS = frozenset({"data", "type", "attributes", "relationships"})
# Ruby type names used in "Must be one of" lists that describe a type rather than values.
TYPE_NAMES = frozenset({"Hash", "File", "String", "Array", "Integer"})
BOOLEAN_VALUES = frozenset({"true", "false", "1", "0"})


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    summary: str


@dataclass
class Param:
    name: str
    required: bool
    nullable: bool
    location: str  # "url", "query" or "body"
    description: str
    schema: dict


@dataclass
class Section:
    key: str
    group_key: str
    routes: list[Route]
    description: str
    params: list[Param] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class Group:
    key: str
    name: str
    description: str


@dataclass
class Documentation:
    groups: dict[str, Group] = field(default_factory=dict)
    sections: list[Section] = field(default_factory=list)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def inline_markdown(node: Tag | None) -> str:
    """Flatten an element to single-line markdown (code, links and emphasis are kept)."""
    if node is None:
        return ""

    def render(element: Tag) -> str:
        parts: list[str] = []
        for child in element.children:
            if isinstance(child, NavigableString):
                parts.append(str(child))
            elif not isinstance(child, Tag):
                continue
            elif child.name == "code":
                parts.append(f"`{normalize(child.get_text())}`")
            elif child.name == "a" and child.get("href"):
                parts.append(f"[{normalize(render(child))}]({child['href']})")
            elif child.name in ("strong", "b"):
                parts.append(f"**{normalize(render(child))}**")
            elif child.name in ("em", "i"):
                parts.append(f"*{normalize(render(child))}*")
            else:
                parts.append(render(child))
        return "".join(parts)

    return normalize(render(node))


def block_markdown(container: Tag | None) -> str:
    """Render the prose that precedes the first sub-heading of an article."""
    if container is None:
        return ""
    blocks: list[str] = []
    for child in container.children:
        if not isinstance(child, Tag):
            continue
        if child.name in ("h2", "h3"):
            break
        if child.name == "pre":
            code = "\n".join(line.rstrip() for line in child.get_text().strip("\n").splitlines())
            if code.strip():
                blocks.append(f"```\n{code}\n```")
        elif child.name in ("ul", "ol"):
            items = [inline_markdown(li) for li in child.find_all("li", recursive=False)]
            blocks.append("\n".join(f"- {item}" for item in items if item))
        elif child.name in ("p", "div"):
            text = inline_markdown(child)
            if text:
                blocks.append(text)
    return "\n\n".join(blocks)


def parse_metadata(cell: Tag) -> dict[str, str]:
    """Read the `Param Type:` / `Notes:` lines stored in a parameter's <pre> block."""
    metadata: dict[str, str] = {}
    current: str | None = None
    for pre in cell.find_all("pre"):
        for raw_line in pre.get_text().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = re.match(r"^(Param Type|Notes):\s*(.*)$", line, re.IGNORECASE)
            if match:
                current = match.group(1).lower()
                metadata[current] = match.group(2).strip()
            elif current:
                metadata[current] = f"{metadata[current]} {line}".strip()
    if "notes" in metadata:
        metadata["notes"] = re.sub(r"^\|\s*", "", metadata["notes"])
    return metadata


def schema_from_validations(
    validations: list[tuple[str, list[str]]], comma_separated: bool
) -> tuple[dict, list[str]]:
    """Translate IT Glue's "Validations" bullets into a JSON schema plus leftover notes."""
    schema: dict = {}
    notes: list[str] = []
    enum: list[str] = []

    for text, codes in validations:
        lowered = text.lower()
        if lowered.startswith("must be one of"):
            values = codes or [v.strip() for v in text.split(":", 1)[-1].strip(" .").split(",") if v.strip()]
            enum.extend(values)
        elif "must be a number" in lowered or "must be an integer" in lowered:
            schema["type"] = "integer"
        elif "must be a string" in lowered:
            schema["type"] = "string"
        elif "must be a hash" in lowered:
            schema["type"] = "object"
        elif "array of nested" in lowered:
            schema["type"] = "array"
            schema["items"] = {"type": "object"}
        elif "must be an array" in lowered or "must be a list" in lowered:
            schema["type"] = "array"
            schema["items"] = {}
        else:
            notes.append(f"Validation: {text}")

    if enum:
        values = list(dict.fromkeys(enum))
        if all(value.lower() in BOOLEAN_VALUES for value in values):
            schema["type"] = "boolean"
        elif set(values) <= TYPE_NAMES:
            notes.append(f"Accepts: {', '.join(values)}")
        elif comma_separated:
            schema.setdefault("type", "string")
            notes.append("Allowed values: " + ", ".join(f"`{value}`" for value in values))
        elif schema.get("type") == "integer" and all(re.fullmatch(r"-?\d+", value) for value in values):
            schema["enum"] = [int(value) for value in values]
        else:
            schema.setdefault("type", "string")
            schema["enum"] = values

    return (schema or {"type": "string"}), notes


def parse_param_row(row: Tag) -> Param | None:
    cells = row.find_all("td", recursive=False)
    if len(cells) < 2:
        return None
    strong = cells[0].find("strong")
    name = normalize(strong.get_text()) if strong else ""
    if not name:
        return None

    small = cells[0].find("small")
    flags = [flag.strip().lower() for flag in normalize(small.get_text()).split(",")] if small else []
    value_cell = cells[1]

    paragraphs = [
        text
        for paragraph in value_cell.find_all("p")
        if paragraph.find_parent("li") is None and (text := inline_markdown(paragraph))
    ]
    validations = [
        (inline_markdown(item), [normalize(code.get_text()) for code in item.find_all("code")])
        for item in value_cell.select("ul > li")
    ]
    metadata = parse_metadata(value_cell)
    notes = metadata.get("notes", "")
    schema, extra_notes = schema_from_validations(validations, "comma separated" in notes.lower())

    description_parts = [" ".join(paragraphs)] if paragraphs else []
    if notes:
        description_parts.append(f"Notes: {notes}")
    description_parts.extend(extra_notes)

    param_type = metadata.get("param type", "").lower()
    if "json body" in param_type:
        location = "body"
    elif param_type.startswith("in url") and "body" not in param_type:
        location = "url"
    elif param_type in ("cgi", "query parameter") or "in url or" in param_type:
        location = "query"
    else:
        location = ""

    return Param(
        name=name,
        required="required" in flags,
        nullable=any("nil allowed" in flag for flag in flags),
        location=location,
        description="\n\n".join(part for part in description_parts if part),
        schema=schema,
    )


def resolve_locations(params: list[Param]) -> None:
    """Give every parameter a location, letting nested names inherit from their root."""
    root_locations = {
        param.name: param.location for param in params if "[" not in param.name and param.location
    }
    for param in params:
        if param.location:
            continue
        root = param.name.split("[", 1)[0]
        if root in root_locations:
            param.location = root_locations[root]
        elif root in BODY_ROOTS:
            param.location = "body"
        else:
            param.location = "query"


def table_after_heading(article: Tag, title: str) -> Tag | None:
    for heading in article.find_all(["h2", "h3"]):
        if normalize(heading.get_text()).lower() == title:
            table = heading.find_next("table")
            if table is not None and article in table.parents:
                return table
    return None


def parse_errors(article: Tag) -> dict[str, str]:
    errors: dict[str, str] = {}
    table = table_after_heading(article, "errors")
    for row in table.find_all("tr") if table else []:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        match = STATUS_CODE_PATTERN.search(normalize(cells[0].get_text()))
        if match:
            errors[match.group(0)] = normalize(cells[1].get_text()) or "Error response"
    return errors


def parse_params(article: Tag) -> list[Param]:
    table = table_after_heading(article, "params")
    params = [param for row in (table.find_all("tr") if table else []) if (param := parse_param_row(row))]
    resolve_locations(params)
    return params


def subtitle_of(heading: Tag) -> str:
    sibling = heading.find_next_sibling()
    if isinstance(sibling, Tag) and "subtitle" in sibling.get("class", []):
        return inline_markdown(sibling)
    return ""


def parse_documentation(html: str) -> Documentation:
    soup = BeautifulSoup(html, "html.parser")
    documentation = Documentation()

    for div in soup.find_all("div", class_=re.compile(r"^page__")):
        key = next((c[len("page__") :] for c in div.get("class", []) if c.startswith("page__")), "")
        if not key or key == "info":
            continue

        headings = div.find_all("h1", recursive=False)
        routes = []
        for heading in headings:
            match = ROUTE_PATTERN.match(normalize(heading.get_text()))
            if match:
                routes.append(Route(match.group(1).lower(), match.group(2), subtitle_of(heading)))

        article = div.find("article")
        details = (article.find("div", class_="methodDetails") or article) if article else None
        description = block_markdown(details)

        if routes:
            section = Section(
                key=key,
                group_key=key.rsplit("__", 1)[0],
                routes=routes,
                description=description,
            )
            if article is not None:
                section.params = parse_params(article)
                section.errors = parse_errors(article)
            documentation.sections.append(section)
        elif headings:
            summary = subtitle_of(headings[0])
            documentation.groups[key] = Group(
                key=key,
                name=normalize(headings[0].get_text()),
                description="\n\n".join(part for part in (summary, description) if part),
            )

    return documentation
