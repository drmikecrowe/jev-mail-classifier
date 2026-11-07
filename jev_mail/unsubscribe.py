from __future__ import annotations

import re

import httpx

# RFC 8058: the List-Unsubscribe-Post value, which is also the form body to POST.
ONE_CLICK = "List-Unsubscribe=One-Click"
TIMEOUT = 20.0


def one_click_url(list_unsubscribe: str, list_unsubscribe_post: str) -> str | None:
    """The https URL to POST under RFC 8058, or None when the email offers no one-click unsubscribe."""
    if list_unsubscribe_post.strip().lower() != ONE_CLICK.lower():
        return None
    for part in re.findall(r"<([^>]*)>", list_unsubscribe):
        url = "".join(part.split())
        if url.lower().startswith("https://"):
            return url
    return None


def unsubscribe(url: str) -> str | None:
    """POSTs the one-click body to `url`. Returns None on a 2xx answer, otherwise why it failed."""
    # httpx follows no redirect by default; RFC 8058 has the sender answer the POST itself, so a 3xx is a failure.
    try:
        response = httpx.post(
            url, content=ONE_CLICK, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=TIMEOUT
        )
    except httpx.HTTPError as exc:
        return f"{type(exc).__name__}: {exc}"
    return None if response.is_success else f"HTTP {response.status_code}"
