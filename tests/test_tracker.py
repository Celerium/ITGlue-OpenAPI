import json
from datetime import date

import pytest

from itglue_openapi.http import FetchError
from itglue_openapi.tracker import SuspiciousSpecError, update_spec

DOCS_URL = "https://docs.test/"
NOTES_URL = "https://notes.test/"


class FakeSite:
    def __init__(self, docs: str, notes: str):
        self.docs, self.notes = docs, notes
        self.notes_down = False

    def __call__(self, url: str) -> str:
        if url == NOTES_URL:
            if self.notes_down:
                raise FetchError("down")
            return self.notes
        return self.docs


@pytest.fixture
def site(developer_html, release_notes_html):
    return FakeSite(developer_html, release_notes_html)


@pytest.fixture
def run(site, tmp_path):
    output, changelog = tmp_path / "ITGlue.json", tmp_path / "CHANGELOG.md"

    def _run(day: date, **kwargs):
        return update_spec(
            output,
            source_url=DOCS_URL,
            release_notes_url=NOTES_URL,
            changelog=changelog,
            today=day,
            fetch=site,
            **kwargs,
        )

    _run.output, _run.changelog = output, changelog
    return _run


def test_first_run_writes_the_spec_with_the_product_version(run):
    result = run(date(2026, 11, 13))

    assert result.changed and result.version == "1.118.132" and result.previous_version is None
    spec = json.loads(run.output.read_text(encoding="utf-8"))
    assert spec["info"]["version"] == "1.118.132"
    assert spec["info"]["x-itglue-product-version"] == "1.118.132"
    assert "Initial specification" in result.release_notes
    assert "## 1.118.132 - 2026-11-13" in run.changelog.read_text(encoding="utf-8")


def test_unchanged_docs_leave_every_file_untouched(run):
    run(date(2026, 11, 13))
    spec_bytes, changelog_bytes = run.output.read_bytes(), run.changelog.read_bytes()
    spec_mtime = run.output.stat().st_mtime_ns

    result = run(date(2026, 11, 14))

    assert not result.changed and result.version == "1.118.132"
    assert run.output.read_bytes() == spec_bytes
    assert run.output.stat().st_mtime_ns == spec_mtime
    assert run.changelog.read_bytes() == changelog_bytes


def test_api_change_with_same_product_version_appends_the_date(run, site):
    run(date(2026, 11, 13))
    site.docs = site.docs.replace("Login URL", "Login URL or hostname")

    result = run(date(2026, 11, 20))

    assert result.changed
    assert result.version == "1.118.132.20261120"
    assert result.previous_version == "1.118.132"
    assert "POST /passwords" in result.diff.changed
    assert json.loads(run.output.read_text(encoding="utf-8"))["info"]["version"] == "1.118.132.20261120"
    changelog = run.changelog.read_text(encoding="utf-8")
    assert changelog.index("1.118.132.20261120") < changelog.index("## 1.118.132 - 2026-11-13")


def test_api_change_with_new_product_version_uses_the_product_version(run, site):
    run(date(2026, 11, 13))
    site.notes = site.notes.replace("IT Glue V1.118.132:", "IT Glue V1.118.133:")
    site.docs = site.docs.replace("Login URL", "Login URL or hostname")

    assert run(date(2026, 11, 20)).version == "1.118.133"


def test_product_version_change_alone_is_not_an_api_change(run, site):
    run(date(2026, 11, 13))
    before = run.output.read_bytes()
    site.notes = site.notes.replace("IT Glue V1.118.132:", "IT Glue V1.118.133:")

    assert not run(date(2026, 11, 20)).changed
    assert run.output.read_bytes() == before


def test_second_change_on_the_same_day_gets_a_revision(run, site):
    run(date(2026, 11, 13))
    site.docs = site.docs.replace("Login URL", "Login URL or hostname")
    assert run(date(2026, 11, 20)).version == "1.118.132.20261120"
    site.docs = site.docs.replace("Login URL or hostname", "Login URL, hostname or IP")

    assert run(date(2026, 11, 20)).version == "1.118.132.20261120.2"


def test_unreadable_release_notes_fall_back_to_the_previous_product_version(run, site):
    run(date(2026, 11, 13))
    site.notes_down = True
    site.docs = site.docs.replace("Login URL", "Login URL or hostname")

    assert run(date(2026, 11, 20)).version == "1.118.132.20261120"


def test_unreadable_release_notes_on_first_run_is_an_error(run, site):
    site.notes_down = True
    with pytest.raises(FetchError):
        run(date(2026, 11, 13))


def test_dry_run_writes_nothing(run, site):
    result = run(date(2026, 11, 13), dry_run=True)

    assert result.changed
    assert not run.output.exists() and not run.changelog.exists()


def test_a_mostly_empty_scrape_does_not_overwrite_the_spec(run, site):
    run(date(2026, 11, 13))
    before = run.output.read_bytes()
    site.docs = site.docs.split('<div class="page__apiv1passwords__create')[0] + "</body></html>"

    with pytest.raises(SuspiciousSpecError):
        run(date(2026, 11, 14))
    assert run.output.read_bytes() == before

    assert run(date(2026, 11, 14), force=True).changed
