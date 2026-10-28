from datetime import datetime, timezone
from typing import Any

import httpx #pour communication avec api github

from gh_screener.domain.exceptions import (
    AuthenticationError,
    GitHubApiError,
    InvalidUsernameError,
    RateLimitError,
)


def raise_for_status(response: httpx.Response, username: str) -> None:
    """Translate an HTTP response into one of our exceptions (or return if OK)."""
    status = response.status_code
    if status < 400:  #ok for 200-399
        return
    if status == 401:  # GitHub says the token is bad or missing
        raise AuthenticationError("GitHub rejected the token", status_code=401)
    if status == 404:  # GitHub has no such user
        raise InvalidUsernameError(f"GitHub user {username!r} not found")
    # Must be checked BEFORE the generic 403 case: GitHub uses 403 for rate limits too.
    if _is_rate_limited(response):
        raise RateLimitError(
            reset_at=_reset_time(response),
            remaining=0,
        )
    if status == 403:  # forbidden but not rate limited -> permission problem
        raise AuthenticationError("Token lacks permission", status_code=403)
    # Timeouts are handled in the client; this covers 5xx and unexpected codes.
    # Message uses only the status code: never headers, never the token.
    raise GitHubApiError(f"GitHub returned HTTP {status}", status_code=status)


def raise_for_graphql_errors(payload: Any, username: str) -> None:
    """GraphQL answers HTTP 200 even on failure, so errors live in the body."""
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if not errors:
        return
    kinds = {e.get("type") for e in errors if isinstance(e, dict)}
    if "NOT_FOUND" in kinds:
        raise InvalidUsernameError(f"GitHub user {username!r} not found")
    if "RATE_LIMITED" in kinds:
        raise RateLimitError()
    raise GitHubApiError("GitHub GraphQL query failed")  # generic, no raw body


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    return (
        response.status_code == 403
        and response.headers.get("x-ratelimit-remaining") == "0"
    )


def _reset_time(response: httpx.Response) -> datetime | None:
    raw = response.headers.get("x-ratelimit-reset")  # unix timestamp
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError):  # header missing or garbage
        return None