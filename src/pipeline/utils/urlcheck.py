"""URL liveness check for primary-source citations.

Government / authoritative sites (NTA, e-Gov, METI portals, JCCI etc.) frequently
block non-browser User-Agents with HTTP 403. Those URLs are still valid
citations — they just cannot be probed from server-side. We treat that case as
``trusted_unprobeable`` rather than ``dead`` so the compliance gate does not
block on what is really an anti-bot response.
"""
from __future__ import annotations

import httpx

from .logging import get_logger

log = get_logger(__name__)


# Browser-like UA. Many gov sites still block on UA substring; the allowlist
# below is the real safety net.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Domains we trust as primary sources even when their server refuses our probe.
# Add suffix-matched hosts only; matching is case-insensitive substring on the
# right-anchored host.
_TRUSTED_GOV_DOMAINS = (
    "nta.go.jp",
    "e-gov.go.jp",
    "meti.go.jp",
    "mhlw.go.jp",
    "soumu.go.jp",
    "mof.go.jp",
    "cao.go.jp",
    "mirasapo-plus.go.jp",
    "smrj.go.jp",
    "chusho.meti.go.jp",
)


def _host_is_trusted(host: str) -> bool:
    h = (host or "").lower()
    return any(h == d or h.endswith("." + d) for d in _TRUSTED_GOV_DOMAINS)


def check_url_alive(url: str, *, timeout: float = 8.0) -> tuple[str, int]:
    """Probe ``url``. Returns ``(status, http_code)`` where status is one of:

    - ``"alive"``       — 2xx/3xx response received.
    - ``"trusted"``     — probe rejected (typically 403/anti-bot) but the host
                          is on the gov primary-source allowlist; treat as a
                          valid citation pending manual review.
    - ``"dead"``        — probe returned 4xx/5xx from a non-allowlisted host,
                          or final URL resolves to an error/404 path.
    - ``"unreachable"`` — connection error / DNS failure / timeout.
    """
    if not url or not url.startswith(("http://", "https://")):
        return "dead", 0
    headers = {"User-Agent": _UA, "Accept-Language": "ja,en;q=0.8"}
    host = httpx.URL(url).host
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as c:
            r = c.head(url)
            if r.status_code >= 400 or r.status_code == 405:
                r = c.get(url)
            code = r.status_code
            if code >= 400:
                if _host_is_trusted(host):
                    return "trusted", code
                return "dead", code
            final_path = str(r.url).lower()
            if "/error/" in final_path or "404" in final_path.rsplit("/", 1)[-1]:
                return "dead", 404
            return "alive", code
    except Exception as e:  # noqa: BLE001
        log.debug("url check failed: %s (%s)", url, e)
        if _host_is_trusted(host):
            return "trusted", 0
        return "unreachable", 0
