"""GitHub API client — issue #6.

Implements :class:`~gh_screener.domain.ports.ProfileRepository` using the
GitHub REST API v3.  All HTTP calls are made with ``httpx`` (synchronous
client); the token is injected at construction time and sent as a Bearer
header on every request.

Data fetched per profile
------------------------
* ``/users/{username}``         → followers, following, public_repos
* ``/users/{username}/repos``   → repository_languages (union of all repos)
* ``/users/{username}/events``  → commits_last_12_months (PushEvents in last
                                   365 days, counted as commits payload sum)

Rate limits
-----------
A read-only token has 5,000 requests per hour.  Each profile costs up to three
requests, so ~1,600 profiles per hour.  No explicit rate-limit handling is
implemented; callers will receive a ``DomainError`` if the API responds with an
unexpected status code.

Dependency rule
---------------
``infra`` may import from ``domain`` only.  It never imports from ``cli`` or
``application``.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable

import httpx

from gh_screener.domain.exceptions import DomainError, ProfileNotFoundError
from gh_screener.domain.models import Profile

_BASE_URL = "https://api.github.com"
_TIMEOUT = 10.0


class GitHubClient:
    """Fetch and normalise GitHub profiles via the REST API.

    Parameters
    ----------
    token:
        A GitHub personal access token.  Must have at least ``public_repo``
        read access (a classic fine-grained read-only token is sufficient).
    """

    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_profile(self, username: str) -> Profile:
        """Fetch a single profile and return a normalised :class:`Profile`."""
        with httpx.Client(
            base_url=_BASE_URL, headers=self._headers, timeout=_TIMEOUT
        ) as client:
            return self._fetch_profile(client, username)

    def get_profiles(self, usernames: Iterable[str]) -> list[Profile]:
        """Fetch multiple profiles, sharing a single HTTP connection pool."""
        with httpx.Client(
            base_url=_BASE_URL, headers=self._headers, timeout=_TIMEOUT
        ) as client:
            return [self._fetch_profile(client, u) for u in usernames]

    def _fetch_profile(self, client: httpx.Client, username: str) -> Profile:
        user_data = self._get_user(client, username)
        languages = self._get_languages(client, username)
        commits = self._get_commits_last_12_months(client, username)

        return Profile(
            username=user_data["login"],
            open_source_projects=user_data.get("public_repos", 0),
            followers=user_data.get("followers", 0),
            following=user_data.get("following", 0),
            repository_languages=frozenset(languages),
            commits_last_12_months=commits,
        )

    def _get_user(self, client: httpx.Client, username: str) -> dict:
        response = client.get(f"/users/{username}")
        if response.status_code == 404:
            raise ProfileNotFoundError(f"No GitHub profile found for {username!r}.")
        _raise_for_status(response, username)
        return response.json()

    def _get_languages(self, client: httpx.Client, username: str) -> set[str]:
        """Return the union of all languages used across the user's public repos."""
        languages: set[str] = set()
        page = 1
        per_page = 100

        while True:
            response = client.get(
                f"/users/{username}/repos",
                params={"per_page": per_page, "page": page, "type": "owner"},
            )
            _raise_for_status(response, username)
            repos = response.json()
            if not repos:
                break
            for repo in repos:
                if repo.get("language"):
                    languages.add(repo["language"])
            if len(repos) < per_page:
                break
            page += 1

        return languages

    def _get_commits_last_12_months(self, client: httpx.Client, username: str) -> int:
        """Count commits pushed by *username* in the last 365 days.

        Uses the public events endpoint (up to 300 events, 10 pages x 30).
        Each ``PushEvent`` contributes ``size`` commits (distinct commits in
        that push).  This is an approximation consistent with what the GitHub
        contribution graph shows for public repositories.
        """
        cutoff = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=365)
        total_commits = 0
        page = 1
        per_page = 100
        exhausted = False

        while page <= 10:
            response = client.get(
                f"/users/{username}/events/public",
                params={"per_page": per_page, "page": page},
            )
            _raise_for_status(response, username)
            events = response.json()
            if not events:
                break

            for event in events:
                if event.get("type") != "PushEvent":
                    continue
                created_at_str = event.get("created_at", "")
                try:
                    created_at = datetime.datetime.fromisoformat(created_at_str)
                except ValueError:
                    continue

                if created_at < cutoff:
                    exhausted = True
                    break

                payload = event.get("payload", {})
                total_commits += payload.get("size", 0)

            if exhausted or len(events) < per_page:
                break
            page += 1

        return total_commits


def _raise_for_status(response: httpx.Response, username: str) -> None:
    """Raise a :class:`~gh_screener.domain.exceptions.DomainError` for non-2xx responses."""
    if response.is_success:
        return
    raise DomainError(
        f"GitHub API returned {response.status_code} for {username!r}: "
        f"{response.text[:200]}"
    )
