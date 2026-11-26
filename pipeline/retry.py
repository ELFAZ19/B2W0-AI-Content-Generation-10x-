"""Retry helper with exponential backoff and jitter for transient API failures."""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class NonRetryableError(RuntimeError):
    """Raised for configuration or validation failures that should not be retried."""


def with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = 3,
    base_delay_s: float = 1.5,
    max_delay_s: float = 15.0,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    """Execute ``fn`` up to ``max_attempts`` times with jittered exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except NonRetryableError:
            raise
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = min(max_delay_s, base_delay_s * (2 ** (attempt - 1)))
            delay *= random.uniform(0.8, 1.2)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc
