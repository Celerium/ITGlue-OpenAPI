import copy

from itglue_openapi.builder import build_spec
from itglue_openapi.diff import comparable, diff_specs, render_markdown
from itglue_openapi.parser import parse_documentation


def make_specs(developer_html):
    old = build_spec(parse_documentation(developer_html), "1.118.131", "1.118.131")
    return old, copy.deepcopy(old)


def test_identical_specs_have_no_diff(developer_html):
    old, new = make_specs(developer_html)
    assert diff_specs(old, new).is_empty


def test_version_bookkeeping_is_not_an_api_change(developer_html):
    old, new = make_specs(developer_html)
    new["info"]["version"] = "1.118.132.20261113"
    new["info"]["x-itglue-product-version"] = "1.118.132"
    assert comparable(old) == comparable(new)
    assert diff_specs(old, new).is_empty


def test_added_and_removed_operations(developer_html):
    old, new = make_specs(developer_html)
    del new["paths"]["/exports"]
    new["paths"]["/widgets"] = {
        "get": {"summary": "List widgets", "responses": {"200": {"description": "ok"}}}
    }

    diff = diff_specs(old, new)

    assert diff.added == ["GET /widgets"]
    assert diff.removed == ["POST /exports"]


def test_parameter_and_body_changes_are_described(developer_html):
    old, new = make_specs(developer_html)
    operation = new["paths"]["/passwords"]["post"]
    operation["parameters"].append(
        {"name": "otp", "in": "query", "required": True, "schema": {"type": "string"}}
    )
    attributes = operation["requestBody"]["content"]["application/vnd.api+json"]["schema"]["properties"][
        "data"
    ]["properties"]["attributes"]
    attributes["properties"]["name"]["type"] = "integer"
    del attributes["properties"]["url"]
    new["paths"]["/passwords"]["get"]["responses"]["429"] = {"description": "Too Many Requests"}

    diff = diff_specs(old, new)

    assert diff.changed["POST /passwords"] == [
        "parameter added: `otp` (query, required)",
        "body field removed: `data.attributes.url`",
        "body field `data.attributes.name`: type `string` → `integer`",
    ]
    assert diff.changed["GET /passwords"] == ["response added: `429` Too Many Requests"]


def test_top_level_changes_outside_paths_are_reported(developer_html):
    old, new = make_specs(developer_html)
    new["servers"].append({"url": "https://api.example.com"})
    assert diff_specs(old, new).other == ["servers"]


def test_markdown_lists_each_kind_of_change(developer_html):
    old, new = make_specs(developer_html)
    del new["paths"]["/exports"]
    new["paths"]["/passwords"]["get"]["summary"] = "Something else"

    markdown = render_markdown(diff_specs(old, new))

    assert "### Removed endpoints\n- `POST /exports`" in markdown
    assert "### Modified endpoints\n- `GET /passwords`\n  - summary changed" in markdown
