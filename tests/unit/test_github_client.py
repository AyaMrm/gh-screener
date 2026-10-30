"""Unit tests for infra/github_client.py — issue #6.

All tests use ``httpx.MockTransport`` (via ``respx`` patterns or a manual
WSGI/ASGI app) to avoid any real network calls.  The GitHub API responses are
minimal JSON objects that contain only the fields our client reads.
"""

from __future__ import annotations

import json

import httpx
import pytest

from gh_screener.domain.exceptions import (
    AuthenticationError,
    GitHubApiError,
    MalformedGitHubDataError,
    ProfileNotFoundError,
    RateLimitError,
)
from gh_screener.domain.models import Profile
from gh_screener.infra.github_client import GitHubClient, _is_env_file

# ---------------------------------------------------------------------------
# Helpers — build a fake httpx transport
# ---------------------------------------------------------------------------

def _make_response(status_code: int, body: object) -> httpx.Response:
    content = json.dumps(body).encode()
    return httpx.Response(status_code, content=content)


class _FakeTransport(httpx.BaseTransport):
    """Routes requests to a simple dict of (method, path) → response."""

    def __init__(self, routes: dict[str, httpx.Response]) -> None:
        # keys are path prefixes, matched in insertion order
        self._routes = routes

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for key, response in self._routes.items():
            if path.startswith(key):
                return response
        raise AssertionError(f"Unexpected request: {request.method} {path}")


def _client_with(routes: dict[str, httpx.Response]) -> GitHubClient:
    """Return a GitHubClient whose HTTP calls are served by *routes*."""
    client = GitHubClient(token="fake-token")
    client._transport = _FakeTransport(routes)
    return client


# We need to patch the httpx.Client used inside GitHubClient._fetch_profile.
# The cleanest way without a third-party library is to monkey-patch httpx.Client
# to accept a ``transport`` kwarg.  Instead, let's override _fetch_profile
# directly by passing a pre-built httpx.Client.

def _patched_get_profile(gh_client: GitHubClient, username: str, routes: dict) -> Profile:
    """Call _fetch_profile with a mock httpx.Client."""
    transport = _FakeTransport(routes)
    with httpx.Client(base_url="https://api.github.com", transport=transport) as http:
        return gh_client._fetch_profile(http, username)


def _patched_scan_env_commits(
    gh_client: GitHubClient, username: str, routes: dict
):
    transport = _FakeTransport(routes)
    with httpx.Client(base_url="https://api.github.com", transport=transport) as http:
        return gh_client._scan_env_commits(http, username)


def test_request_converts_transport_errors_to_github_api_errors() -> None:
    def fail_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    transport = httpx.MockTransport(fail_request)
    client = GitHubClient(token="fake-token")

    with (
        httpx.Client(base_url="https://api.github.com", transport=transport) as http,
        pytest.raises(GitHubApiError, match="Could not connect to the GitHub API"),
    ):
        client._request(http, "GET", "/users/octocat")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_USER_RESPONSE = _make_response(200, {
    "login": "octocat",
    "public_repos": 8,
    "followers": 100,
    "following": 50,
})

_REPOS_RESPONSE = _make_response(200, [
    {"name": "python-repo", "language": "Python", "fork": False, "private": False},
    {"name": "go-repo", "language": "Go", "fork": False, "private": False},
    {"name": "empty-repo", "language": None, "fork": False, "private": False},
])

_CONTRIBUTIONS_RESPONSE = _make_response(200, {
    "data": {
        "user": {
            "contributionsCollection": {"totalCommitContributions": 5},
        },
    },
})

_ZERO_CONTRIBUTIONS_RESPONSE = _make_response(200, {
    "data": {
        "user": {
            "contributionsCollection": {"totalCommitContributions": 0},
        },
    },
})


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_get_profile_returns_correct_username() -> None:
    routes = {
        "/graphql": _CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.username == "octocat"


def test_get_profile_counts_public_repositories() -> None:
    routes = {
        "/graphql": _CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.public_repositories == 3


def test_get_profile_rejects_malformed_repository_data() -> None:
    malformed_repos = _make_response(200, [
        {"name": "missing-fork-flag", "language": "Python", "private": False},
    ])
    routes = {
        "/users/octocat": _USER_RESPONSE,
        "/users/octocat/repos": malformed_repos,
    }

    with pytest.raises(MalformedGitHubDataError):
        _patched_get_profile(GitHubClient(token="fake-token"), "octocat", routes)


def test_get_profile_maps_followers_and_following() -> None:
    routes = {
        "/graphql": _CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.followers == 100
    assert profile.following == 50


def test_get_profile_collects_languages_from_repos() -> None:
    routes = {
        "/graphql": _CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.repository_languages == frozenset({"Python", "Go"})


def test_get_profile_counts_commit_contributions() -> None:
    routes = {
        "/graphql": _CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.commits_last_12_months == 5


def test_null_language_repos_are_excluded() -> None:
    repos_with_nulls = _make_response(200, [
        {"name": "one", "language": None, "fork": False, "private": False},
        {"name": "two", "language": None, "fork": False, "private": False},
    ])
    routes = {
        "/graphql": _ZERO_CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": repos_with_nulls,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.repository_languages == frozenset()


def test_public_repo_count_includes_forks_but_excludes_private_repos() -> None:
    repos_with_fork = _make_response(200, [
        {"name": "python", "language": "Python", "fork": False, "private": False},
        {"name": "go-fork", "language": "Go", "fork": True, "private": False},
        {"name": "private", "language": "Rust", "fork": False, "private": True},
    ])
    routes = {
        "/graphql": _ZERO_CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": repos_with_fork,
        "/users/octocat": _USER_RESPONSE,
    }

    profile = _patched_get_profile(GitHubClient(token="fake-token"), "octocat", routes)

    assert profile.repository_languages == frozenset({"Python"})
    assert profile.public_repositories == 2


def test_zero_contributions_gives_zero_commits() -> None:
    routes = {
        "/graphql": _ZERO_CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.commits_last_12_months == 0


# ---------------------------------------------------------------------------
# Invalid GraphQL contribution data is rejected
# ---------------------------------------------------------------------------

def test_invalid_graphql_contribution_count_is_rejected() -> None:
    invalid_count = _make_response(200, {
        "data": {
            "user": {
                "contributionsCollection": {"totalCommitContributions": -1},
            },
        },
    })
    routes = {
        "/graphql": invalid_count,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")

    with pytest.raises(MalformedGitHubDataError):
        _patched_get_profile(client, "octocat", routes)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_404_raises_profile_not_found_error() -> None:
    not_found = _make_response(404, {"message": "Not Found"})
    routes = {
        "/graphql": _ZERO_CONTRIBUTIONS_RESPONSE,
        "/users/ghost/repos": _make_response(200, []),
        "/users/ghost": not_found,
    }
    client = GitHubClient(token="fake-token")

    with pytest.raises(ProfileNotFoundError):
        _patched_get_profile(client, "ghost", routes)


def test_non_404_api_error_raises_domain_error() -> None:
    server_error = _make_response(500, {"message": "Internal Server Error"})
    routes = {
        "/graphql": _ZERO_CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _make_response(200, []),
        "/users/octocat": server_error,
    }
    client = GitHubClient(token="fake-token")

    with pytest.raises(GitHubApiError):
        _patched_get_profile(client, "octocat", routes)


def test_401_raises_authentication_error() -> None:
    unauthorized = _make_response(401, {"message": "Bad credentials"})
    routes = {"/users/octocat": unauthorized}

    with pytest.raises(AuthenticationError):
        _patched_get_profile(GitHubClient(token="fake-token"), "octocat", routes)


def test_rate_limit_error_raises_domain_error() -> None:
    rate_limited = _make_response(403, {"message": "API rate limit exceeded"})
    routes = {
        "/graphql": _ZERO_CONTRIBUTIONS_RESPONSE,
        "/users/octocat/repos": _make_response(200, []),
        "/users/octocat": rate_limited,
    }
    client = GitHubClient(token="fake-token")

    with pytest.raises(RateLimitError):
        _patched_get_profile(client, "octocat", routes)


def test_env_commit_scan_detects_env_file_in_target_users_commit() -> None:
    routes = {
        "/repos/octocat/demo/commits/abc123": _make_response(200, {
            "files": [{"filename": "config/.env.production"}],
        }),
        "/repos/octocat/demo/commits": _make_response(200, [
            {"sha": "abc123", "author": {"login": "octocat"}},
        ]),
        "/users/octocat/repos": _make_response(200, [
            {"name": "demo", "fork": False, "private": False},
        ]),
    }
    client = GitHubClient(token="fake-token")

    result = _patched_scan_env_commits(client, "octocat", routes)

    assert result.found is True


def test_env_commit_scan_ignores_commit_attributed_to_someone_else() -> None:
    routes = {
        "/repos/octocat/demo/commits": _make_response(200, [
            {"sha": "abc123", "author": {"login": "other-user"}},
        ]),
        "/users/octocat/repos": _make_response(200, [
            {"name": "demo", "fork": False, "private": False},
        ]),
    }
    client = GitHubClient(token="fake-token")

    result = _patched_scan_env_commits(client, "octocat", routes)

    assert result.found is False
    assert result.complete is True


def test_missing_repository_during_scan_is_not_reported_as_missing_user() -> None:
    routes = {
        "/repos/octocat/demo/commits": _make_response(404, {"message": "Not Found"}),
        "/users/octocat/repos": _make_response(200, [
            {"name": "demo", "fork": False, "private": False},
        ]),
    }

    with pytest.raises(GitHubApiError):
        _patched_scan_env_commits(
            GitHubClient(token="fake-token"), "octocat", routes
        )


@pytest.mark.parametrize(
    "filename",
    [".env", "config/.env.local", ".env.production.local"],
)
def test_env_file_matcher_detects_env_files(filename: str) -> None:
    assert _is_env_file(filename) is True


@pytest.mark.parametrize(
    "filename",
    [
        ".env.example",
        ".env.production.example",
        ".env.local.sample",
        ".env.development.dist",
        "config/.env.sample",
        ".env.template.local",
        ".env.defaults",
        "example.env",
        None,
    ],
)
def test_env_file_matcher_ignores_templates_and_unrelated_files(filename: object) -> None:
    assert _is_env_file(filename) is False
