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
from dataclasses import replace

from gh_screener.domain.exceptions import (
    DomainError,
    RateLimitError,
    SecretScanIncompleteError,
)
from gh_screener.domain.filter.builder import build_filters
from gh_screener.domain.filters import matches_all
from gh_screener.domain.models import (
    ScreeningCriteria,
    ScreeningError,
    ScreeningResult,
)
from gh_screener.domain.ports import ProfileRepository


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

    for index, username in enumerate(usernames):
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
            result.errors.append(ScreeningError(username=username, message=message))
            result.errors.extend(
                ScreeningError(
                    username=skipped_username,
                    message=(
                        "Not processed because the GitHub API rate limit was reached."
                    ),
                )
                for skipped_username in usernames[index + 1 :]
            )
            break
        except DomainError as exc:
            result.errors.append(ScreeningError(username=username, message=str(exc)))
            continue

        if matches_all(profile, filters):
            result.matched_profiles.append(profile)
        else:
            result.rejected_profiles.append(profile)

    return result
