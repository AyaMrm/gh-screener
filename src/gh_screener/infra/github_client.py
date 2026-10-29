"""GitHub API client — issue #6.

Implements :class:`~gh_screener.domain.ports.ProfileRepository` using the
GitHub REST API v3.  All HTTP calls are made with ``httpx`` (synchronous
client); the token is injected at construction time and sent as a Bearer
header on every request.

Data fetched per profile
------------------------
* ``/users/{username}``         → login, followers, following
* ``/users/{username}/repos``   → non-fork project count and languages
* ``/users/{username}/events``  → commits_last_12_months (PushEvents in last
                                   365 days, counted as commits payload sum)

Rate limits
-----------
Rate limits and HTTP failures are translated into typed domain exceptions by
``infra.error``. The optional secret scan is separately bounded.

Dependency rule
---------------
``infra`` may import from ``domain`` only.  It never imports from ``cli`` or
``application``.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from pathlib import PurePosixPath

import httpx

from gh_screener.domain.exceptions import DomainError
from gh_screener.domain.models import EnvCommitScanResult, Profile, Repo
from gh_screener.infra.error import raise_for_status
from gh_screener.infra.mapper import (
    build_profile,
    follow_counts_from_github,
    repos_from_github,
    username_from_github,
)

_BASE_URL = "https://api.github.com"
_TIMEOUT = 10.0
_SECRET_SCAN_MAX_REPOSITORIES = 20
_SECRET_SCAN_MAX_COMMITS_PER_REPOSITORY = 15


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

    def scan_env_commits(self, username: str) -> EnvCommitScanResult:
        with httpx.Client(
            base_url=_BASE_URL, headers=self._headers, timeout=_TIMEOUT
        ) as client:
            return self._scan_env_commits(client, username)

    def _scan_env_commits(
        self, client: httpx.Client, username: str
    ) -> EnvCommitScanResult:
        response = client.get(
            f"/users/{username}/repos",
            params={
                "per_page": _SECRET_SCAN_MAX_REPOSITORIES + 1,
                "page": 1,
                "type": "owner",
                "sort": "updated",
                "direction": "desc",
            },
        )
        raise_for_status(response, username)
        repositories = repos_from_github(response.json())

        complete = len(repositories) <= _SECRET_SCAN_MAX_REPOSITORIES
        for repository in repositories[:_SECRET_SCAN_MAX_REPOSITORIES]:
            name = repository.name

            commits_response = client.get(
                f"/repos/{username}/{name}/commits",
                params={
                    "author": username,
                    "per_page": _SECRET_SCAN_MAX_COMMITS_PER_REPOSITORY + 1,
                    "page": 1,
                },
            )
            raise_for_status(commits_response, username)
            commits = commits_response.json()
            if not isinstance(commits, list):
                raise DomainError("GitHub returned an invalid commit list.")

            if len(commits) > _SECRET_SCAN_MAX_COMMITS_PER_REPOSITORY:
                complete = False

            for commit in commits[:_SECRET_SCAN_MAX_COMMITS_PER_REPOSITORY]:
                if not isinstance(commit, dict):
                    raise DomainError("GitHub returned an invalid commit record.")
                author = commit.get("author")
                author_login = author.get("login") if isinstance(author, dict) else None
                if (
                    not isinstance(author_login, str)
                    or author_login.casefold() != username.casefold()
                ):
                    continue
                sha = commit.get("sha")
                if not isinstance(sha, str) or not sha:
                    raise DomainError("GitHub returned a commit without a valid SHA.")

                detail_response = client.get(f"/repos/{username}/{name}/commits/{sha}")
                raise_for_status(detail_response, username)
                detail = detail_response.json()
                files = detail.get("files") if isinstance(detail, dict) else None
                if not isinstance(files, list):
                    raise DomainError("GitHub returned commit details without a file list.")

                if any(
                    _is_env_file(file.get("filename"))
                    for file in files
                    if isinstance(file, dict)
                ):
                    return EnvCommitScanResult(found=True, complete=True)
                if "next" in detail_response.links:
                    complete = False

        return EnvCommitScanResult(found=False, complete=complete)

    def _fetch_profile(self, client: httpx.Client, username: str) -> Profile:
        user_data = self._get_user(client, username)
        repositories = self._get_repositories(client, username)
        commits = self._get_commits_last_12_months(client, username)
        followers, following = follow_counts_from_github(user_data)

        return build_profile(
            username=username_from_github(user_data),
            repos=repositories,
            commits=commits,
            followers=followers,
            following=following,
        )

    def _get_user(self, client: httpx.Client, username: str) -> dict:
        response = client.get(f"/users/{username}")
        raise_for_status(response, username, is_user_lookup=True)
        return response.json()

    def _get_repositories(self, client: httpx.Client, username: str) -> list[Repo]:
        """Return all repositories owned by the user, across API pages."""
        repositories: list[Repo] = []
        page = 1
        per_page = 100

        while True:
            response = client.get(
                f"/users/{username}/repos",
                params={"per_page": per_page, "page": page, "type": "owner"},
            )
            raise_for_status(response, username)
            repos = repos_from_github(response.json())
            if not repos:
                break
            repositories.extend(repos)
            if len(repos) < per_page:
                break
            page += 1

        return repositories

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
            raise_for_status(response, username)
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


def _is_env_file(filename: object) -> bool:
    if not isinstance(filename, str):
        return False
    basename = PurePosixPath(filename).name.casefold()
    if basename == ".env":
        return True
    if not basename.startswith(".env."):
        return False
    
    template_markers = {"default", "defaults", "dist", "example", "sample", "template"}
    suffix = basename[len(".env."):].split(".", maxsplit=1)[0]
    return suffix not in template_markers
