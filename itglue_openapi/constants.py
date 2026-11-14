"""Shared constants."""

from pathlib import Path

SOURCE_URL = "https://api.itglue.com/developer/"
RELEASE_NOTES_URL = "https://help.itglue.kaseya.com/help/Content/0-HOME/Release-Notes.htm"
REPOSITORY_URL = "https://github.com/Celerium/ITGlue-OpenAPI"

DEFAULT_OUTPUT = Path("ITGlue.json")
DEFAULT_CHANGELOG = Path("CHANGELOG.md")

USER_AGENT = f"ITGlue-OpenAPI-watcher (+{REPOSITORY_URL})"
OPENAPI_VERSION = "3.0.3"
CONTENT_TYPE = "application/vnd.api+json"

# Key inside `info` that remembers which IT Glue product version the spec was last released under.
PRODUCT_VERSION_KEY = "x-itglue-product-version"
