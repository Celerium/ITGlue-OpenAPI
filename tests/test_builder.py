import pytest

from itglue_openapi.builder import build_spec
from itglue_openapi.parser import Documentation, parse_documentation

BODY = "application/vnd.api+json"


@pytest.fixture
def spec(developer_html):
    return build_spec(parse_documentation(developer_html), "1.118.132", "1.118.132")


def parameters(operation):
    return {(p["in"], p["name"]): p for p in operation["parameters"]}


def test_every_documented_route_becomes_an_operation(spec):
    assert set(spec["paths"]) == {
        "/passwords",
        "/organizations/{organization_id}/relationships/passwords",
        "/exports",
    }
    assert set(spec["paths"]["/passwords"]) == {"get", "post", "delete"}
    assert set(spec["paths"]["/organizations/{organization_id}/relationships/passwords"]) == {"get", "post"}


def test_operation_ids_are_unique_and_readable(spec):
    ids = [op["operationId"] for item in spec["paths"].values() for op in item.values()]
    assert len(ids) == len(set(ids))
    assert spec["paths"]["/passwords"]["get"]["operationId"] == "listPasswords"
    assert spec["paths"]["/passwords"]["delete"]["operationId"] == "bulkDeletePasswords"
    nested = spec["paths"]["/organizations/{organization_id}/relationships/passwords"]
    assert nested["get"]["operationId"] == "listPasswordsForOrganizations"


def test_summaries_descriptions_and_tags(spec):
    operation = spec["paths"]["/passwords"]["get"]
    assert operation["summary"] == "List or search passwords."
    assert "[sorting](https://example.com/sorting)" in operation["description"]
    assert operation["tags"] == ["Passwords"]
    tags = {tag["name"]: tag.get("description") for tag in spec["tags"]}
    assert set(tags) == {"Passwords", "Exports"}  # Exports has no group section, so it has no description
    assert "login credential" in tags["Passwords"] and tags["Exports"] is None


def test_url_params_are_path_params_only_on_routes_that_contain_them(spec):
    plain = parameters(spec["paths"]["/passwords"]["get"])
    nested = parameters(spec["paths"]["/organizations/{organization_id}/relationships/passwords"]["get"])

    assert ("path", "organization_id") not in plain
    assert ("query", "organization_id") not in plain
    assert nested[("path", "organization_id")]["required"] is True
    assert nested[("path", "organization_id")]["schema"] == {"type": "integer"}


def test_query_parameters_are_typed(spec):
    params = parameters(spec["paths"]["/passwords"]["get"])

    assert ("query", "filter") not in params  # replaced by its filter[...] children
    assert params[("query", "filter[archived]")]["schema"] == {"type": "boolean"}
    assert params[("query", "filter[id]")]["schema"] == {"type": "integer"}
    sort = params[("query", "sort")]
    assert sort["schema"] == {"type": "string"}
    assert "`created_at`" in sort["description"]
    assert "Comma separated values" in sort["description"]


def test_non_path_url_param_is_a_query_param(spec):
    params = parameters(spec["paths"]["/passwords"]["post"])
    assert params[("query", "show_password")]["schema"] == {"type": "boolean"}
    assert all(name != "data" for _, name in params)


def test_request_body_is_built_from_nested_data_params(spec):
    body = spec["paths"]["/passwords"]["post"]["requestBody"]
    schema = body["content"][BODY]["schema"]
    data = schema["properties"]["data"]

    assert body["required"] is True and schema["required"] == ["data"]
    assert data["required"] == ["type", "attributes"]
    assert data["properties"]["type"]["enum"] == ["passwords"]
    attributes = data["properties"]["attributes"]
    assert attributes["required"] == ["name"]
    assert attributes["properties"]["name"] == {"type": "string"}
    assert attributes["properties"]["url"] == {"type": "string", "nullable": True, "description": "Login URL"}


def test_bulk_body_is_an_array_of_objects(spec):
    data = spec["paths"]["/passwords"]["delete"]["requestBody"]["content"][BODY]["schema"]["properties"][
        "data"
    ]
    assert data["type"] == "array"
    assert data["items"]["required"] == ["attributes"]
    assert data["items"]["properties"]["attributes"]["properties"]["id"] == {"type": "integer"}


def test_body_documented_without_data_wrapper_is_wrapped(spec):
    operation = spec["paths"]["/exports"]["post"]
    data = operation["requestBody"]["content"][BODY]["schema"]["properties"]["data"]
    assert set(data["properties"]) == {"type", "attributes"}
    assert not any(p["in"] == "query" for p in operation["parameters"])


def test_get_operations_never_have_a_request_body(spec):
    assert "requestBody" not in spec["paths"]["/passwords"]["get"]


def test_error_responses_are_collected(spec):
    responses = spec["paths"]["/passwords"]["get"]["responses"]
    assert responses["401"] == {"description": "Unauthorized"}
    assert responses["404"] == {"description": "Not Found"}
    assert "200" in responses


def test_spec_is_stable_between_runs(developer_html):
    first = build_spec(parse_documentation(developer_html), "1.0.0")
    second = build_spec(parse_documentation(developer_html), "1.0.0")
    assert first == second


def test_rejects_pages_without_api_operations():
    with pytest.raises(ValueError, match="No API operations"):
        build_spec(Documentation(), "1.0.0")


def test_spec_is_valid_openapi(spec):
    validator = pytest.importorskip("openapi_spec_validator")
    validator.validate(spec)
