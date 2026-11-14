from datetime import date

import pytest

from itglue_openapi.versioning import next_version, parse_product_version

TODAY = date(2026, 11, 13)


def test_reads_the_current_release_from_the_release_notes(release_notes_html):
    assert parse_product_version(release_notes_html) == "1.118.132"


def test_falls_back_to_first_version_link_without_current_release_heading():
    html = '<a href="x">IT Glue V1.118.131: November 5, 2026</a><a href="y">IT Glue V1.118.129: Oct</a>'
    assert parse_product_version(html) == "1.118.131"


def test_release_notes_without_versions_are_rejected():
    with pytest.raises(ValueError):
        parse_product_version("<html><body>Maintenance page</body></html>")


def test_new_product_version_is_used_as_is():
    assert next_version("1.118.132", TODAY, "1.118.131.20261105", "1.118.131") == "1.118.132"


def test_first_ever_version_is_the_product_version():
    assert next_version("1.118.132", TODAY) == "1.118.132"


def test_unchanged_product_version_gets_the_date_appended():
    assert next_version("1.118.132", TODAY, "1.118.132", "1.118.132") == "1.118.132.20261113"


def test_second_change_on_the_same_day_gets_a_revision():
    assert next_version("1.118.132", TODAY, "1.118.132.20261113", "1.118.132") == "1.118.132.20261113.2"
    assert next_version("1.118.132", TODAY, "1.118.132.20261113.2", "1.118.132") == "1.118.132.20261113.3"


def test_change_on_a_later_day_does_not_reuse_a_revision():
    assert (
        next_version("1.118.132", date(2026, 11, 14), "1.118.132.20261113.2", "1.118.132")
        == "1.118.132.20261114"
    )
