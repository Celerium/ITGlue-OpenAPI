"""IT Glue does not publish an API version, so the product version stands in for it."""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

VERSION_PATTERN = re.compile(r"\bV(\d+(?:\.\d+)+)\b", re.IGNORECASE)
REVISION_PATTERN = re.compile(r"^(?P<base>.+\.\d{8})(?:\.(?P<revision>\d+))?$")


def parse_product_version(html: str) -> str:
    """Read the current IT Glue product version from the release notes landing page."""
    soup = BeautifulSoup(html, "html.parser")
    links = [a for a in soup.find_all("a") if VERSION_PATTERN.search(a.get_text(" ", strip=True))]
    if not links:
        raise ValueError("Could not find any product version in the release notes page.")

    heading = soup.find(string=re.compile(r"^\s*current release\s*$", re.IGNORECASE))
    if heading is not None:
        following = next((a for a in heading.find_all_next("a") if a in links), None)
        if following is not None:
            links.insert(0, following)

    match = VERSION_PATTERN.search(links[0].get_text(" ", strip=True))
    assert match is not None
    return match.group(1)


def next_version(
    product_version: str,
    today: date,
    previous_version: str | None = None,
    previous_product_version: str | None = None,
) -> str:
    """Pick the version for a spec that is known to have changed.

    * New product version since the last release -> the product version (`1.118.132`).
    * Same product version as the last release   -> product version + date (`1.118.132.20261113`).
    * Same candidate as the previous release     -> a numeric revision is appended (`...20261113.2`).
    """
    candidate = product_version
    if previous_product_version == product_version:
        candidate = f"{product_version}.{today:%Y%m%d}"

    if previous_version:
        match = REVISION_PATTERN.match(previous_version)
        previous_base = match.group("base") if match else previous_version
        if candidate == previous_base:
            revision = int(match.group("revision") or 1) if match else 1
            return f"{candidate}.{revision + 1}"
    return candidate
