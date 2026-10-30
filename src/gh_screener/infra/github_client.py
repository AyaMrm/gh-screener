"""GitHub API client — issue #6.

Implements :class:`~gh_screener.domain.ports.ProfileRepository` using the
GitHub REST API v3.  All HTTP calls are made with ``httpx`` (synchronous
client); the token is injected at construction time and sent as a Bearer
header on every request.

Data fetched per profile
------------------------
* ``/users/{username}``         → login, followers, following
* ``/users/{username}/repos``   → public repository count and languages
* ``/graphql``                  → commits_last_12_months (contributions over
                                   the selected 365-day period)

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
from typing import Any

import httpx

from gh_screener.domain.exceptions import (
    DomainError,
    GitHubApiError,
    MalformedGitHubDataError,
    RateLimitError,
)
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
_SECRET_SCAN_MAX_COMMIT_DETAILS = 40
_ENV_TEMPLATE_MARKERS = frozenset(
    {"default", "defaults", "dist", "example", "sample", "template"}
)
_COMMIT_CONTRIBUTIONS_QUERY = """
query($username: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $username) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
    }
  }
}
"""


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

    def _request(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        try:
            return client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            raise GitHubApiError(
                "Could not connect to the GitHub API. Check your network and retry."
            ) from exc

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
        response = self._request(
            client,
            "GET",
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
        inspected_commit_details = 0
        for repository in repositories[:_SECRET_SCAN_MAX_REPOSITORIES]:
            name = repository.name

            commits_response = self._request(
                client,
                "GET",
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

                if inspected_commit_details >= _SECRET_SCAN_MAX_COMMIT_DETAILS:
                    return EnvCommitScanResult(found=False, complete=False)

                detail_response = self._request(
                    client,
                    "GET",
                    f"/repos/{username}/{name}/commits/{sha}",
                )
                raise_for_status(detail_response, username)
                detail = detail_response.json()
                files = detail.get("files") if isinstance(detail, dict) else None
                if not isinstance(files, list):
                    raise DomainError("GitHub returned commit details without a file list.")
                inspected_commit_details += 1

                if any(
                    _is_env_file(file.get("filename"))
                    for file in files
                    if isinstance(file, dict)
                ):
                    return EnvCommitScanResult(found=True, complete=True)
                if inspected_commit_details >= _SECRET_SCAN_MAX_COMMIT_DETAILS:
                    return EnvCommitScanResult(found=False, complete=False)
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
        response = self._request(client, "GET", f"/users/{username}")
        raise_for_status(response, username, is_user_lookup=True)
        return response.json()

    def _get_repositories(self, client: httpx.Client, username: str) -> list[Repo]:
        """Return all repositories owned by the user, across API pages."""
        repositories: list[Repo] = []
        page = 1
        per_page = 100

        while True:
            response = self._request(
                client,
                "GET",
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
        end = datetime.datetime.now(tz=datetime.UTC)
        start = end - datetime.timedelta(days=365)
        response = self._request(
            client,
            "POST",
            "/graphql",
            json={
                "query": _COMMIT_CONTRIBUTIONS_QUERY,
                "variables": {
                    "username": username,
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                },
            },
        )
        raise_for_status(response, username)

        payload = response.json()
        if not isinstance(payload, dict):
            raise GitHubApiError("GitHub could not return commit contributions.")
        errors = payload.get("errors")
        if errors:
            messages = []
            if isinstance(errors, list):
                messages = [
                    error["message"]
                    for error in errors
                    if isinstance(error, dict)
                    and isinstance(error.get("message"), str)
                ]
            if (
                response.headers.get("x-ratelimit-remaining") == "0"
                or any("rate limit" in message.casefold() for message in messages)
            ):
                raw_reset = response.headers.get("x-ratelimit-reset")
                try:
                    reset_at = datetime.datetime.fromtimestamp(
                        int(raw_reset), tz=datetime.UTC
                    )
                except (TypeError, ValueError):
                    reset_at = None
                raise RateLimitError(reset_at=reset_at)
            raise GitHubApiError("GitHub could not return commit contributions.")

        data = payload.get("data")
        user = data.get("user") if isinstance(data, dict) else None
        collection = (
            user.get("contributionsCollection") if isinstance(user, dict) else None
        )
        count = (
            collection.get("totalCommitContributions")
            if isinstance(collection, dict)
            else None
        )
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise MalformedGitHubDataError(
                "GitHub returned an invalid commit contribution count."
            )
        return count


def _is_env_file(filename: object) -> bool:
    if not isinstance(filename, str):
        return False
    basename = PurePosixPath(filename).name.casefold()
    if basename == ".env":
        return True
    if not basename.startswith(".env."):
        return False

    suffixes = basename.removeprefix(".env.").split(".")
    return not any(suffix in _ENV_TEMPLATE_MARKERS for suffix in suffixes)
