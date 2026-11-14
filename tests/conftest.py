from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def developer_html() -> str:
    return (FIXTURES / "developer.html").read_text(encoding="utf-8")


@pytest.fixture
def release_notes_html() -> str:
    return (FIXTURES / "release_notes.html").read_text(encoding="utf-8")
