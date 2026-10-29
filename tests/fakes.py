"""Fake (in-memory) implementations of domain ports for use in tests.

These fakes replace the real GitHub client so that unit tests for the use
case and CLI can run without any network access or a real GitHub token.
"""

from __future__ import annotations

from collections.abc import Iterable

from gh_screener.domain.exceptions import ProfileNotFoundError
from gh_screener.domain.models import Profile


class FakeProfileRepository:
    """An in-memory :class:`~gh_screener.domain.ports.ProfileRepository`.

    Parameters
    ----------
    profiles:
        A mapping of *username → Profile*.  If a requested username is not
        present a :class:`~gh_screener.domain.exceptions.ProfileNotFoundError`
        is raised, mirroring real GitHub-client behaviour.

    Examples
    --------
    >>> repo = FakeProfileRepository({"octocat": Profile(username="octocat")})
    >>> repo.get_profile("octocat")
    Profile(username='octocat', ...)
    """

    def __init__(self, profiles: dict[str, Profile] | None = None) -> None:
        self._profiles: dict[str, Profile] = profiles or {}

    def get_profile(self, username: str) -> Profile:
        """Return the profile for *username* or raise ProfileNotFoundError."""
        try:
            return self._profiles[username]
        except KeyError:
            raise ProfileNotFoundError(
                f"No GitHub profile found for {username!r}."
            )

    def get_profiles(self, usernames: Iterable[str]) -> list[Profile]:
        """Return profiles for all *usernames* in order."""
        return [self.get_profile(u) for u in usernames]
