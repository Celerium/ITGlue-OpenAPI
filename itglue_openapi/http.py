"""Minimal HTTP client with retries."""

from __future__ import annotations

import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constants import USER_AGENT


class FetchError(RuntimeError):
    """Raised when a page cannot be downloaded."""


def fetch_text(url: str, *, timeout: tuple[int, int] = (10, 60)) -> str:
    session = requests.Session()
    retry = Retry(
        total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=("GET",)
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    try:
        response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"Could not download {url}: {exc}") from exc

    # `requests` falls back to ISO-8859-1 for text/html without a charset; these pages are UTF-8.
    match = re.search(r"charset=([\w-]+)", response.headers.get("Content-Type", ""), re.IGNORECASE)
    return response.content.decode(match.group(1) if match else "utf-8", errors="replace")
