"""URL liveness check shared by research and factcheck nodes."""
from __future__ import annotations

import httpx

from .logging import get_logger

log = get_logger(__name__)


def check_url_alive(url: str, *, timeout: float = 8.0) -> tuple[bool, int]:
    """HEAD with GET fallback. Detects soft-404 redirects.

    Returns (is_alive, status_code). status_code is 0 for connection errors.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False, 0
    headers = {"User-Agent": "dougasakusei/0.1"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as c:
            r = c.head(url)
            if r.status_code >= 400 or r.status_code == 405:
                r = c.get(url)
            if r.status_code >= 400:
                return False, r.status_code
            final_path = str(r.url).lower()
            if "/error/" in final_path or "404" in final_path.rsplit("/", 1)[-1]:
                return False, 404
            return True, r.status_code
    except Exception as e:  # noqa: BLE001
        log.debug("url check failed: %s (%s)", url, e)
        return False, 0


def filter_alive_urls(urls: list[str]) -> tuple[list[str], list[tuple[str, int]]]:
    """Returns (alive_urls, dead_url_with_status_list). De-dupes input."""
    seen: dict[str, tuple[bool, int]] = {}
    for u in urls:
        if u and u not in seen:
            seen[u] = check_url_alive(u)
    alive = [u for u, (ok, _) in seen.items() if ok]
    dead = [(u, st) for u, (ok, st) in seen.items() if not ok]
    return alive, dead
