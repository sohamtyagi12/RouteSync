"""Tiny in-memory rate limiter for the AI agent endpoints.

Protects the free Gemini quota: each user gets AGENT_RATE_LIMIT calls per
AGENT_RATE_WINDOW seconds (default 10 per hour), and the whole site gets
AGENT_GLOBAL_LIMIT calls per AGENT_GLOBAL_WINDOW seconds (default 100 per day).

Counters live in this process's memory, so they reset when the server restarts
or Render's free tier goes to sleep. That is fine for a demo; use Redis if you
ever run several server processes.
"""
import math
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_lock = threading.Lock()
_user_calls = defaultdict(deque)
_global_calls = deque()


def _int_env(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, default)), 1)
    except ValueError:
        return default


def _seconds_to_wait(calls: deque, limit: int, window: int, now: float) -> int:
    while calls and now - calls[0] >= window:
        calls.popleft()
    if len(calls) >= limit:
        return math.ceil(window - (now - calls[0]))
    return 0


def _too_many(wait: int, reason: str) -> HTTPException:
    minutes = max(1, math.ceil(wait / 60))
    return HTTPException(
        status_code=429,
        detail=f"{reason} Try again in about {minutes} minute(s).",
        headers={"Retry-After": str(wait)},
    )


def check_agent_rate_limit(user) -> None:
    """Call at the start of an AI endpoint. Raises 429 when a limit is reached."""
    now = time.monotonic()
    with _lock:
        calls = _user_calls[user.id]
        wait = _seconds_to_wait(calls, _int_env("AGENT_RATE_LIMIT", 10), _int_env("AGENT_RATE_WINDOW", 3600), now)
        if wait:
            raise _too_many(wait, "You have reached your limit for AI requests.")
        wait = _seconds_to_wait(_global_calls, _int_env("AGENT_GLOBAL_LIMIT", 100), _int_env("AGENT_GLOBAL_WINDOW", 86400), now)
        if wait:
            raise _too_many(wait, "The daily limit for AI requests on this site has been reached.")
        calls.append(now)
        _global_calls.append(now)


def reset() -> None:
    """Clear all counters (used by tests)."""
    with _lock:
        _user_calls.clear()
        _global_calls.clear()
