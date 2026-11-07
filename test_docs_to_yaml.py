import unittest
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

module_spec = spec_from_file_location("docs_to_yaml", Path(__file__).with_name("docs-to-yaml.py"))
if module_spec is None or module_spec.loader is None:
  raise ImportError("Could not load docs-to-yaml.py")
docs_to_yaml = module_from_spec(module_spec)
module_spec.loader.exec_module(docs_to_yaml)


DOCUMENTATION = """
<div class="page__info"><h1>Overview</h1></div>
<div class="page__apiv1organizations">
  <h1>GET&nbsp;/organizations/:id</h1>
  <article>
    <p>Returns an organization.</p>
    <h2>Params</h2>
    <table>
      <tr><th>Parameter</th><th>Description</th></tr>
      <tr>
        <td><strong>id</strong><small>required</small></td>
        <td>Organization identifier <div>Validations: Must be a number.</div></td>
      </tr>
      <tr>
        <td><strong>include_archived</strong><small>optional</small></td>
        <td>Whether archived records are included <div>Validations: Must be true or false.</div></td>
      </tr>
    </table>
    <h2>Errors</h2>
    <table>
      <tr><th>Code</th><th>Description</th></tr>
      <tr><td>404</td><td>Organization not found</td></tr>
    </table>
  </article>
</div>
<div class="page__apiv1attachments">
  <h1>POST&nbsp;/attachments</h1>
  <article>
    <h2>Params</h2>
    <table>
      <tr><th>Parameter</th><th>Description</th></tr>
      <tr>
        <td><strong>data</strong><small>required</small></td>
        <td>Validations: Must be an Array of nested elements Metadata: Param Type: JSON Body Param</td>
      </tr>
      <tr>
        <td><strong>data[_]</strong><small>optional</small></td>
        <td>Validations: Must be a Hash</td>
      </tr>
    </table>
  </article>
</div>
"""


class BuildOpenApiSpecTests(unittest.TestCase):
    def test_extracts_path_parameters_types_errors_and_version(self) -> None:
        spec = docs_to_yaml.build_openapi_spec(DOCUMENTATION, date(2026, 11, 6))

        self.assertEqual(spec["info"]["version"], "1.0.0.20261106")
        operation = spec["paths"]["/organizations/{id}"]["get"]
        parameters = {(parameter["in"], parameter["name"]): parameter for parameter in operation["parameters"]}
        self.assertTrue(parameters[("path", "id")]["required"])
        self.assertEqual(parameters[("path", "id")]["schema"]["type"], "integer")
        self.assertEqual(parameters[("query", "include_archived")]["schema"]["type"], "boolean")
        self.assertEqual(operation["responses"]["404"]["description"], "Organization not found")

        create_operation = spec["paths"]["/attachments"]["post"]
        self.assertNotIn("data", {parameter["name"] for parameter in create_operation["parameters"]})
        body_schema = create_operation["requestBody"]["content"]["application/vnd.api+json"]["schema"]
        self.assertEqual(body_schema["properties"]["data"]["type"], "array")
        self.assertTrue(create_operation["requestBody"]["required"])

    def test_rejects_pages_without_api_operations(self) -> None:
        with self.assertRaisesRegex(ValueError, "No API operations"):
            docs_to_yaml.build_openapi_spec("<div class='page__info'><h1>Overview</h1></div>")


if __name__ == "__main__":
    unittest.main()