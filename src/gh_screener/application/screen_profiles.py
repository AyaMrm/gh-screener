"""Screening use case — issue #12.

Orchestrates the full screening workflow:

1. Fetch each profile from the repository (GitHub API via infra layer).
2. Apply every active criterion from *criteria*.
3. Bucket profiles into matched / rejected / errors.
4. Return the consolidated :class:`~gh_screener.domain.models.ScreeningResult`.

Dependency rule
---------------
This module may import from ``domain`` only.
It receives a ``ProfileRepository`` through its function signature so that
the ``infra`` layer is never imported here directly — callers (``cli`` or
tests) inject the concrete implementation.
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from gh_screener.domain.exceptions import (
    DomainError,
    RateLimitError,
    SecretScanIncompleteError,
)
from gh_screener.domain.filter.builder import build_filters
from gh_screener.domain.filters import matches_all
from gh_screener.domain.models import (
    Profile,
    ScreeningCriteria,
    ScreeningError,
    ScreeningResult,
)
from gh_screener.domain.ports import ProfileRepository

_MAX_CONCURRENT_PROFILES = 3


@dataclass(frozen=True)
class _ProfileOutcome:
    profile: Profile | None = None
    error: ScreeningError | None = None
    rate_limited: bool = False


def _fetch_profile(
    username: str,
    criteria: ScreeningCriteria,
    repository: ProfileRepository,
) -> _ProfileOutcome:
    try:
        profile = repository.get_profile(username)
        if criteria.exclude_env_committers:
            scan = repository.scan_env_commits(username)
            if not scan.complete and not scan.found:
                raise SecretScanIncompleteError(
                    "The .env commit scan reached its limit before it could "
                    "confirm whether this profile is clear."
                )
            profile = replace(profile, has_committed_env_files=scan.found)
    except RateLimitError as exc:
        message = str(exc)
        if exc.reset_at is not None:
            message += f" Retry after {exc.reset_at.isoformat()}."
        return _ProfileOutcome(
            error=ScreeningError(username=username, message=message),
            rate_limited=True,
        )
    except DomainError as exc:
        return _ProfileOutcome(error=ScreeningError(username=username, message=str(exc)))

    return _ProfileOutcome(profile=profile)


def screen_profiles(
    usernames: Iterable[str],
    criteria: ScreeningCriteria,
    repository: ProfileRepository,
) -> ScreeningResult:
    """Screen *usernames* against *criteria* using *repository* for data.

    Parameters
    ----------
    usernames:
        Iterable of already-validated GitHub usernames.
    criteria:
        The active screening criteria built by
        :func:`~gh_screener.domain.criteria.build_criteria`.
    repository:
        A :class:`~gh_screener.domain.ports.ProfileRepository` implementation
        that knows how to fetch profiles (injected by the caller).

    Returns
    -------
    ScreeningResult
        Contains three lists: matched profiles, rejected profiles, and errors
        (usernames that could not be fetched or evaluated).
    """
    result = ScreeningResult()
    filters = build_filters(criteria)
    usernames = list(usernames)

    with ThreadPoolExecutor(max_workers=_MAX_CONCURRENT_PROFILES) as executor:
        for start in range(0, len(usernames), _MAX_CONCURRENT_PROFILES):
            batch = usernames[start : start + _MAX_CONCURRENT_PROFILES]
            outcomes = executor.map(
                lambda username: _fetch_profile(username, criteria, repository), batch
            )
            rate_limited = False
            for outcome in outcomes:
                if outcome.error is not None:
                    result.errors.append(outcome.error)
                    rate_limited = rate_limited or outcome.rate_limited
                elif outcome.profile is not None:
                    if matches_all(outcome.profile, filters):
                        result.matched_profiles.append(outcome.profile)
                    else:
                        result.rejected_profiles.append(outcome.profile)

            if rate_limited:
                result.errors.extend(
                    ScreeningError(
                        username=username,
                        message=(
                            "Not processed because the GitHub API rate limit was reached."
                        ),
                    )
                    for username in usernames[start + len(batch) :]
                )
                break

    return result
