"""
orbit_retry.py — Orbit360
Configurable retry decorator and helper for Playwright operations.

Provides two ways to add retry behaviour:

  1. @retry decorator — wraps a function definition
  2. retry_call()    — wraps a single call inline (useful for lambdas)

Both accept an optional on_exhaust callback that fires after all attempts
fail.  Pass manual_prompt from orbit_context to give the analyst a chance to
fix the page state before the script raises.

Usage:

    from orbit360.utils.orbit_retry import retry, retry_call
    from orbit360.backend.orbit_context import manual_prompt

    # Decorator form
    @retry(attempts=3, delay=2, logger=logger)
    def open_worklist():
        worklist_btn.click()

    # Decorator with manual fallback after all retries
    @retry(
        attempts=3,
        on_exhaust=lambda name, _: manual_prompt(
            f"'{name}' failed after retries — fix it then click Continue",
            "Resuming after manual fix",
        )
    )
    def select_hold_reason():
        dropdown.select_option("3M-3M UPDATE ISSUE")

    # Inline form (no decorator needed)
    retry_call(
        lambda: frame.get_by_role("button", name="OK").click(),
        attempts=3,
        delay=1.5,
        logger=logger,
    )
"""
from __future__ import annotations

import functools
import logging
import time
from typing import Callable, Optional, Sequence, Tuple, Type


def retry(
    attempts: int = 3,
    delay: float = 2.0,
    exceptions: Sequence[Type[BaseException]] = (Exception,),
    on_exhaust: Optional[Callable[[str, BaseException], None]] = None,
    logger: Optional[logging.Logger] = None,
):
    """
    Decorator factory — retry the wrapped function up to *attempts* times.

    Args:
        attempts:    Total number of tries (first attempt + retries).
        delay:       Seconds to wait between attempts.
        exceptions:  Exception types that trigger a retry.  Any other
                     exception propagates immediately.
        on_exhaust:  Called as on_exhaust(fn_name, last_exception) after
                     all attempts fail.  If it does not raise, the last
                     exception is re-raised automatically.  Typical use:
                     pass manual_prompt to pause and let the analyst fix.
        logger:      Logs each retry at WARNING level if provided.
    """
    _exc_tuple: Tuple[Type[BaseException], ...] = tuple(exceptions)

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Optional[BaseException] = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except _exc_tuple as exc:
                    last_exc = exc
                    if logger:
                        logger.warning(
                            f"retry | {fn.__name__} | attempt {attempt}/{attempts} | {exc}"
                        )
                    if attempt < attempts:
                        time.sleep(delay)
            if on_exhaust is not None:
                on_exhaust(fn.__name__, last_exc)  # type: ignore[arg-type]
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


def retry_call(
    fn: Callable,
    *args,
    attempts: int = 3,
    delay: float = 2.0,
    exceptions: Sequence[Type[BaseException]] = (Exception,),
    on_exhaust: Optional[Callable[[str, BaseException], None]] = None,
    logger: Optional[logging.Logger] = None,
    **kwargs,
):
    """
    Non-decorator version of retry — call *fn* with *args*/*kwargs*,
    retrying on failure up to *attempts* times.

    Returns the value returned by *fn* on success.

    Args:
        fn:          Any callable.
        *args:       Positional arguments forwarded to fn.
        attempts:    Total number of tries.
        delay:       Seconds to wait between attempts.
        exceptions:  Exception types that trigger a retry.
        on_exhaust:  Called as on_exhaust(name, last_exception) after all
                     attempts fail.
        logger:      Logs each retry at WARNING level if provided.
        **kwargs:    Keyword arguments forwarded to fn.
    """
    _exc_tuple: Tuple[Type[BaseException], ...] = tuple(exceptions)
    name = getattr(fn, "__name__", repr(fn))
    last_exc: Optional[BaseException] = None

    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except _exc_tuple as exc:
            last_exc = exc
            if logger:
                logger.warning(
                    f"retry_call | {name} | attempt {attempt}/{attempts} | {exc}"
                )
            if attempt < attempts:
                time.sleep(delay)

    if on_exhaust is not None:
        on_exhaust(name, last_exc)  # type: ignore[arg-type]
    raise last_exc  # type: ignore[misc]
