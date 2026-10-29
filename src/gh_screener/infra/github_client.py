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
import re
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

import httpx

from gh_screener.domain.exceptions import (
    GitHubApiError,
    InvalidProfileError,
    MalformedGitHubDataError,
)
from gh_screener.domain.models import Profile, Repo

from .error import raise_for_graphql_errors, raise_for_status
from .mapper import (
    build_profile,
    commit_count_from_graphql,
    follow_counts_from_github,
    repos_from_github,
)

REST_URL = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"

# Which Profile fields require which API call (this is what `needs` is matched against)
REPO_FIELDS = frozenset({"open_source_projects", "repository_languages"})
COMMIT_FIELDS = frozenset({"commits_last_12_months"})
FOLLOW_FIELDS = frozenset({"followers", "following"})
SECRET_FIELDS = frozenset({"has_committed_env_files"})

# Letters, digits, hyphens, max 39 chars. Also blocks URL tricks like "../".
_USERNAME = re.compile(r"[A-Za-z0-9-]{1,39}")

# With no date arguments, contributionsCollection covers the last 12 months
_COMMITS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection { totalCommitContributions }
  }
}
"""


class GitHubClient:  # satisfies ProfileRepository (a Protocol, no inheritance needed)
    def __init__(
        self,
        token: str,
        *,
        needs: Iterable[str] = (),
        http_client: httpx.Client | None = None,  # tests inject a MockTransport client here
        per_page: int = 100,
    ) -> None:
        self._needs = frozenset(needs)  # fields the filters asked for
        self._http = http_client or httpx.Client(timeout=10.0)  # real client in production
        self._per_page = per_page
        # The token lives only in this private header. It is never logged or printed.
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        self._cache: dict[str, Profile] = {}  # lowercase username -> Profile

    def get_profile(self, username: str) -> Profile:
        name = username.strip()
        if not _USERNAME.fullmatch(name):  # reject before any network call
            raise InvalidProfileError(f"{username!r} is not a valid GitHub username")
        key = name.lower()  # GitHub usernames are case-insensitive
        if key in self._cache:  # asking twice costs zero requests
            return self._cache[key]

        # Each block runs only if the filters need that data
        needs_repos = self._needs & (REPO_FIELDS | SECRET_FIELDS)
        repos = self._fetch_repos(name) if needs_repos else []

        commits = self._fetch_commits(name) if self._needs & COMMIT_FIELDS else 0

        has_committed_env_files = (
            self._fetch_committed_env_files(name, repos)
            if self._needs & SECRET_FIELDS
            else False
        )

        followers, following = (
            self._fetch_follow_counts(name) if self._needs & FOLLOW_FIELDS else (0, 0)
        )

        profile = build_profile(name, repos, commits, followers, following)
        if self._needs & SECRET_FIELDS:
            profile = replace(
                profile,
                has_committed_env_files=has_committed_env_files,
            )
        self._cache[key] = profile
        return profile

    def get_profiles(self, usernames: Iterable[str]) -> list[Profile]:
        # Stops at the first failure. The application layer should call get_profile
        # per user and collect ScreeningError so one bad user doesn't stop the rest.
        return [self.get_profile(username) for username in usernames]

    def _fetch_committed_env_files(
            self, username: str, repos: list[Repo]
    ) -> bool:
        for repo in repos:
            page = 1

            while True:
                commits = self._request(
                    "GET",
                    f"{REST_URL}/repos/{username}/{repo.name}/commits",
                    username,
                    params={"per_page": self._per_page, "page": page},
                )

                for commit in commits:
                    details = self._request(
                        "GET",
                        f"{REST_URL}/repos/{username}/{repo.name}/commits/{commit['sha']}",
                        username,
                    )

                    for file in details.get("files", []):
                        filename = file.get("filename", "").split("/")[-1]

                        if filename == ".env":
                            return True

                if len(commits) < self._per_page:
                    break

                page += 1

        return False

    def _fetch_repos(self, username: str) -> list[Repo]:
        repos: list[Repo] = []
        page = 1
        while True:  # a user can have many pages of repositories
            batch = self._request(
                "GET",
                f"{REST_URL}/users/{username}/repos",
                username,
                params={"per_page": self._per_page, "page": page, "type": "owner"},
            )
            repos.extend(repos_from_github(batch))  # validates + converts the page
            if len(batch) < self._per_page:  # a short page means it was the last one
                return repos
            page += 1

    def _fetch_commits(self, username: str) -> int:
        payload = self._request(
            "POST",
            GRAPHQL_URL,
            username,
            json={"query": _COMMITS_QUERY, "variables": {"login": username}},
        )
        raise_for_graphql_errors(payload, username)  # GraphQL hides errors inside HTTP 200
        return commit_count_from_graphql(payload)

    def _fetch_follow_counts(self, username: str) -> tuple[int, int]:
        raw = self._request("GET", f"{REST_URL}/users/{username}", username)
        return follow_counts_from_github(raw)

    def _request(self, method: str, url: str, username: str, **kwargs: Any) -> Any:
        try:
            response = self._http.request(method, url, headers=self._headers, **kwargs)
        except httpx.HTTPError as error:  # timeout, DNS failure, connection reset
            # Static message: never include the request, which holds the token
            raise GitHubApiError("Could not reach GitHub (network error or timeout)") from error
        raise_for_status(response, username)  # HTTP errors become our exceptions
        try:
            return response.json()
        except ValueError as error:  # body is not valid JSON
            raise MalformedGitHubDataError("GitHub returned invalid JSON") from error
