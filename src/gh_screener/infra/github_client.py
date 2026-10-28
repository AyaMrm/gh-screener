import re
from collections.abc import Iterable
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
        repos = self._fetch_repos(name) if self._needs & REPO_FIELDS else []
        commits = self._fetch_commits(name) if self._needs & COMMIT_FIELDS else 0
        followers, following = (
            self._fetch_follow_counts(name) if self._needs & FOLLOW_FIELDS else (0, 0)
        )

        profile = build_profile(name, repos, commits, followers, following)
        self._cache[key] = profile
        return profile

    def get_profiles(self, usernames: Iterable[str]) -> list[Profile]:
        # Stops at the first failure. The application layer should call get_profile
        # per user and collect ScreeningError so one bad user doesn't stop the rest.
        return [self.get_profile(username) for username in usernames]

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