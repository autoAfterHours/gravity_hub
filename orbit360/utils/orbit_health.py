"""
orbit_health.py — Orbit360
Pre-run environment health checks.

Performs a lightweight HTTP check against a target URL before Playwright
even opens a browser.  Fails fast and clearly when the environment is down,
on VPN issues, or DNS can't resolve — saving analysts from waiting through
a full browser launch only to hit a timeout.

Usage in a test script run() function:

    from orbit360.utils.orbit_health import assert_reachable

    def run(playwright):
        assert_reachable("https://your-cac-server/3M_360App", logger=logger)
        # ... rest of the test
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class HealthResult:
    """Result of a single URL reachability check."""

    url: str
    reachable: bool
    status_code: Optional[int]
    latency_ms: float
    error: Optional[str]

    def __str__(self) -> str:
        if self.reachable:
            return f"OK [{self.status_code}] {self.latency_ms:.0f}ms  {self.url}"
        return f"UNREACHABLE  {self.error}  {self.url}"


def check_url(
    url: str,
    timeout: float = 10.0,
    _method: str = "HEAD",
) -> HealthResult:
    """
    Send a lightweight HTTP request to *url* and return a HealthResult.

    Uses HEAD by default so no response body is downloaded.  Automatically
    retries with GET if the server returns 405 Method Not Allowed.

    Never raises — always returns a HealthResult so callers can decide
    whether to hard-fail or just log a warning.
    """
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method=_method)
        req.add_header("User-Agent", "Orbit360-HealthCheck/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = (time.monotonic() - start) * 1000
            return HealthResult(
                url=url,
                reachable=True,
                status_code=resp.status,
                latency_ms=round(latency, 1),
                error=None,
            )
    except urllib.error.HTTPError as exc:
        latency = (time.monotonic() - start) * 1000
        # 405 → retry with GET
        if exc.code == 405 and _method == "HEAD":
            return check_url(url, timeout=timeout, _method="GET")
        # Any HTTP response (4xx, 5xx) means the server is reachable
        return HealthResult(
            url=url,
            reachable=True,
            status_code=exc.code,
            latency_ms=round(latency, 1),
            error=str(exc),
        )
    except urllib.error.URLError as exc:
        latency = (time.monotonic() - start) * 1000
        return HealthResult(
            url=url,
            reachable=False,
            status_code=None,
            latency_ms=round(latency, 1),
            error=str(exc.reason),
        )
    except Exception as exc:  # noqa: BLE001
        latency = (time.monotonic() - start) * 1000
        return HealthResult(
            url=url,
            reachable=False,
            status_code=None,
            latency_ms=round(latency, 1),
            error=str(exc),
        )


def assert_reachable(
    url: str,
    timeout: float = 10.0,
    logger: Optional[logging.Logger] = None,
) -> HealthResult:
    """
    Check *url* and raise RuntimeError with a clear message if unreachable.
    Logs the result at INFO (success) or ERROR (failure) if *logger* is given.

    Usage:
        assert_reachable(
            "https://XRDCWTWEBCAC21B.HCA.CORPAD.NET/3M_360App",
            logger=logger,
        )
    """
    result = check_url(url, timeout=timeout)
    if logger:
        if result.reachable:
            logger.info(f"Health check passed | {result}")
        else:
            logger.error(f"Health check FAILED | {result}")
    if not result.reachable:
        raise RuntimeError(
            f"Environment unreachable — run aborted before browser opened.\n"
            f"URL:   {url}\n"
            f"Error: {result.error}\n\n"
            "Check VPN connection, network access, and that the server is up."
        )
    return result


def check_many(
    urls: List[str],
    timeout: float = 10.0,
    logger: Optional[logging.Logger] = None,
) -> List[HealthResult]:
    """
    Check multiple URLs and return all results.  Never raises.
    Useful for a pre-run sweep across several environments or endpoints.

    Usage:
        results = check_many([
            "https://server-a/3M_360App",
            "https://server-b/3M_360App",
        ], logger=logger)
        all_up = all(r.reachable for r in results)
    """
    results: List[HealthResult] = []
    for url in urls:
        r = check_url(url, timeout=timeout)
        if logger:
            lvl = logging.INFO if r.reachable else logging.WARNING
            logger.log(lvl, f"Health | {r}")
        results.append(r)
    return results
