import pytest

from itglue_openapi import cli, tracker
from itglue_openapi.http import FetchError


@pytest.fixture
def offline(monkeypatch, developer_html, release_notes_html):
    def fake_fetch(url: str) -> str:
        return release_notes_html if "notes" in url else developer_html

    monkeypatch.setattr(tracker, "fetch_text", fake_fetch)


def args(tmp_path, *extra):
    return [
        "--source-url", "https://docs.test/",
        "--release-notes-url", "https://notes.test/",
        "--output", str(tmp_path / "ITGlue.json"),
        "--changelog", str(tmp_path / "CHANGELOG.md"),
        *extra,
    ]  # fmt: skip


def read_outputs(path):
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines())


def test_writes_outputs_and_release_notes_when_changed(offline, tmp_path, capsys):
    github_output, notes = tmp_path / "gh.txt", tmp_path / "notes.md"

    code = cli.main(args(tmp_path, "--github-output", str(github_output), "--release-notes-file", str(notes)))

    assert code == 0
    assert read_outputs(github_output) == {
        "changed": "true",
        "version": "1.118.132",
        "tag": "v1.118.132",
        "previous_version": "",
        "product_version": "1.118.132",
    }
    assert "Initial specification" in notes.read_text(encoding="utf-8")
    assert "Wrote" in capsys.readouterr().out


def test_reports_no_change_on_the_second_run(offline, tmp_path, capsys):
    cli.main(args(tmp_path))
    github_output = tmp_path / "gh.txt"
    notes = tmp_path / "notes.md"

    assert (
        cli.main(args(tmp_path, "--github-output", str(github_output), "--release-notes-file", str(notes)))
        == 0
    )

    assert read_outputs(github_output)["changed"] == "false"
    assert not notes.exists()
    assert "No API changes detected" in capsys.readouterr().out


def test_returns_error_code_when_the_docs_cannot_be_fetched(monkeypatch, tmp_path, capsys):
    def broken(url: str) -> str:
        raise FetchError("boom")

    monkeypatch.setattr(tracker, "fetch_text", broken)

    assert cli.main(args(tmp_path)) == 1
    assert "boom" in capsys.readouterr().err
    assert not (tmp_path / "ITGlue.json").exists()
