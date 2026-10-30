from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest

from gh_screener.config import get_github_token
from gh_screener.domain.exceptions import AuthenticationError, InvalidUsernameError
from gh_screener.infra.github_client import GitHubClient

try:
    _GITHUB_TOKEN: str | None = get_github_token()
except RuntimeError:
    _GITHUB_TOKEN = None

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        _GITHUB_TOKEN is None,
        reason="Set GITHUB_TOKEN in the environment or .env to run live API tests.",
    ),
]


@pytest.fixture
def github_client() -> Iterator[GitHubClient]:
    assert _GITHUB_TOKEN is not None
    client = GitHubClient(token=_GITHUB_TOKEN)
    try:
        yield client
    finally:
        client.close()


def test_fetches_an_existing_github_user(github_client: GitHubClient) -> None:
    profile = github_client.get_profile("octocat")

    assert profile.username.casefold() == "octocat"
    assert profile.public_repositories >= 0
    assert profile.commit_contributions_last_12_months >= 0


def test_unknown_github_user_raises_not_found(
    github_client: GitHubClient,
) -> None:
    username = f"ghs{uuid4().hex[:32]}"

    with pytest.raises(InvalidUsernameError):
        github_client.get_profile(username)


def test_invalid_token_is_rejected() -> None:
    client = GitHubClient(token="ghs_invalid_token_for_integration_test")
    try:
        with pytest.raises(AuthenticationError):
            client.get_profile("octocat")
    finally:
        client.close()
