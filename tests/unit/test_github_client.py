"""Unit tests for infra/github_client.py — issue #6.

All tests use ``httpx.MockTransport`` (via ``respx`` patterns or a manual
WSGI/ASGI app) to avoid any real network calls.  The GitHub API responses are
minimal JSON objects that contain only the fields our client reads.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from gh_screener.domain.exceptions import DomainError, ProfileNotFoundError
from gh_screener.domain.models import Profile
from gh_screener.infra.github_client import GitHubClient

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW_ISO = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

_USER_RESPONSE = _make_response(200, {
    "login": "octocat",
    "public_repos": 8,
    "followers": 100,
    "following": 50,
})

_REPOS_RESPONSE = _make_response(200, [
    {"language": "Python"},
    {"language": "Go"},
    {"language": None},       # repos with no language should be ignored
])

_EVENTS_RESPONSE = _make_response(200, [
    {
        "type": "PushEvent",
        "created_at": _NOW_ISO,
        "payload": {"size": 3},
    },
    {
        "type": "PushEvent",
        "created_at": _NOW_ISO,
        "payload": {"size": 2},
    },
    {
        "type": "WatchEvent",  # non-push events are ignored
        "created_at": _NOW_ISO,
        "payload": {},
    },
])

_EMPTY_EVENTS = _make_response(200, [])


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_get_profile_returns_correct_username() -> None:
    routes = {
        "/users/octocat/events": _EVENTS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.username == "octocat"


def test_get_profile_maps_public_repos_to_open_source_projects() -> None:
    routes = {
        "/users/octocat/events": _EVENTS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.open_source_projects == 8


def test_get_profile_maps_followers_and_following() -> None:
    routes = {
        "/users/octocat/events": _EVENTS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.followers == 100
    assert profile.following == 50


def test_get_profile_collects_languages_from_repos() -> None:
    routes = {
        "/users/octocat/events": _EVENTS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.repository_languages == frozenset({"Python", "Go"})


def test_get_profile_counts_push_event_commits() -> None:
    routes = {
        "/users/octocat/events": _EVENTS_RESPONSE,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    # 3 + 2 from the two PushEvents; WatchEvent is ignored
    assert profile.commits_last_12_months == 5


def test_null_language_repos_are_excluded() -> None:
    repos_with_nulls = _make_response(200, [
        {"language": None},
        {"language": None},
    ])
    routes = {
        "/users/octocat/events": _EMPTY_EVENTS,
        "/users/octocat/repos": repos_with_nulls,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.repository_languages == frozenset()


def test_no_events_gives_zero_commits() -> None:
    routes = {
        "/users/octocat/events": _EMPTY_EVENTS,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.commits_last_12_months == 0


# ---------------------------------------------------------------------------
# Events older than 365 days are excluded
# ---------------------------------------------------------------------------

def test_old_push_events_are_not_counted() -> None:
    old_date = (
        datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=400)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    old_events = _make_response(200, [
        {"type": "PushEvent", "created_at": old_date, "payload": {"size": 99}},
    ])
    routes = {
        "/users/octocat/events": old_events,
        "/users/octocat/repos": _REPOS_RESPONSE,
        "/users/octocat": _USER_RESPONSE,
    }
    client = GitHubClient(token="fake-token")
    profile = _patched_get_profile(client, "octocat", routes)

    assert profile.commits_last_12_months == 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_404_raises_profile_not_found_error() -> None:
    not_found = _make_response(404, {"message": "Not Found"})
    routes = {
        "/users/ghost/events": _EMPTY_EVENTS,
        "/users/ghost/repos": _make_response(200, []),
        "/users/ghost": not_found,
    }
    client = GitHubClient(token="fake-token")

    with pytest.raises(ProfileNotFoundError):
        _patched_get_profile(client, "ghost", routes)


def test_non_404_api_error_raises_domain_error() -> None:
    server_error = _make_response(500, {"message": "Internal Server Error"})
    routes = {
        "/users/octocat/events": _EMPTY_EVENTS,
        "/users/octocat/repos": _make_response(200, []),
        "/users/octocat": server_error,
    }
    client = GitHubClient(token="fake-token")

    with pytest.raises(DomainError):
        _patched_get_profile(client, "octocat", routes)


def test_rate_limit_error_raises_domain_error() -> None:
    rate_limited = _make_response(403, {"message": "API rate limit exceeded"})
    routes = {
        "/users/octocat/events": _EMPTY_EVENTS,
        "/users/octocat/repos": _make_response(200, []),
        "/users/octocat": rate_limited,
    }
    client = GitHubClient(token="fake-token")

    with pytest.raises(DomainError):
        _patched_get_profile(client, "octocat", routes)


def test_env_commit_scan_detects_env_file_in_target_users_commit() -> None:
    routes = {
        "/repos/octocat/demo/commits/abc123": _make_response(200, {
            "files": [{"filename": "config/.env.production"}],
        }),
        "/repos/octocat/demo/commits": _make_response(200, [
            {"sha": "abc123", "author": {"login": "octocat"}},
        ]),
        "/users/octocat/repos": _make_response(200, [{"name": "demo"}]),
    }
    client = GitHubClient(token="fake-token")

    result = _patched_scan_env_commits(client, "octocat", routes)

    assert result.found is True


def test_env_commit_scan_ignores_commit_attributed_to_someone_else() -> None:
    routes = {
        "/repos/octocat/demo/commits": _make_response(200, [
            {"sha": "abc123", "author": {"login": "other-user"}},
        ]),
        "/users/octocat/repos": _make_response(200, [{"name": "demo"}]),
    }
    client = GitHubClient(token="fake-token")

    result = _patched_scan_env_commits(client, "octocat", routes)

    assert result.found is False
    assert result.complete is True
