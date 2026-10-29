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

from gh_screener.domain.exceptions import DomainError
from gh_screener.domain.filter.commits import filter_commits
from gh_screener.domain.filter.projects import filter_projects
from gh_screener.domain.filter.secrets import filter_secrets
from gh_screener.domain.models import (
    Profile,
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

    for username in usernames:
        try:
            profile = repository.get_profile(username)
        except DomainError as exc:
            result.errors.append(ScreeningError(username=username, message=str(exc)))
            continue

        if _matches_all_criteria(profile, criteria):
            result.matched_profiles.append(profile)
        else:
            result.rejected_profiles.append(profile)

    return result


def _matches_all_criteria(profile: Profile, criteria: ScreeningCriteria) -> bool:
    """Return ``True`` if *profile* satisfies every active criterion.

    When *criteria* is empty (no option selected) every profile matches.
    Each individual filter returns ``True`` when its criterion is not active,
    so the calls are always safe to make.

    The preferred-language check is performed here directly: a profile must
    use *all* of the requested languages (exact set membership).  A dedicated
    ``filter_languages`` function will replace this once issue #9 (Part C) is
    merged; at that point this helper can simply delegate to it.
    """
    if criteria.is_empty:
        return True

    if criteria.exclude_env_committers and not filter_secrets(profile, criteria):
        return False

    if not filter_commits(profile, criteria):
        return False

    if not filter_projects(profile, criteria):
        return False

    return not (
        criteria.preferred_languages
        and not criteria.preferred_languages.issubset(profile.repository_languages)
    )
