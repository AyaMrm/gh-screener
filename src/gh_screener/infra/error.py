from datetime import UTC, datetime

import httpx  # pour communication avec api github

from gh_screener.domain.exceptions import (
    AuthenticationError,
    GitHubApiError,
    InvalidUsernameError,
    RateLimitError,
)


def raise_for_status(
    response: httpx.Response,
    username: str,
    *,
    is_user_lookup: bool = False,
) -> None:
    """Translate an HTTP response into one of our exceptions (or return if OK)."""
    status = response.status_code
    if status < 400:  #ok for 200-399
        return
    if status == 401:  # GitHub says the token is bad or missing
        raise AuthenticationError("GitHub rejected the token", status_code=401)
    if status == 404 and is_user_lookup:
        raise InvalidUsernameError(f"GitHub user {username!r} not found")
    # Must be checked BEFORE the generic 403 case: GitHub uses 403 for rate limits too.
    if _is_rate_limited(response):
        raise RateLimitError(
            reset_at=_reset_time(response),
            remaining=0,
        )
    if status == 403:  # forbidden but not rate limited -> permission problem
        raise AuthenticationError("Token lacks permission", status_code=403)
    if status == 404:
        raise GitHubApiError(
            f"GitHub resource not found for {username!r}", status_code=404
        )
    # Timeouts are handled in the client; this covers 5xx and unexpected codes.
    # Message uses only the status code: never headers, never the token.
    raise GitHubApiError(f"GitHub returned HTTP {status}", status_code=status)


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code == 429:
        return True
    if response.status_code != 403:
        return False
    return (
        response.headers.get("x-ratelimit-remaining") == "0"
        or "rate limit" in response.text.casefold()
    )


def _reset_time(response: httpx.Response) -> datetime | None:
    raw = response.headers.get("x-ratelimit-reset")  # unix timestamp
    try:
        return datetime.fromtimestamp(int(raw), tz=UTC)
    except (TypeError, ValueError):  # header missing or garbage
        return None
