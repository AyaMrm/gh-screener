from typing import Any

from gh_screener.domain.exceptions import MalformedGitHubDataError
from gh_screener.domain.models import Profile, Repo


def repo_from_github(raw: Any) -> Repo:
    """Convert ONE raw GitHub repository dict into a Repo."""
    if not isinstance(raw, dict):  # e.g. GitHub sent a string or null
        raise MalformedGitHubDataError(
            f"Expected a repository object, got {type(raw).__name__}"
        )
    name = raw.get("name")
    if not isinstance(name, str) or not name:  # name is required
        raise MalformedGitHubDataError("Repository has no valid 'name'")
    is_fork = raw.get("fork")
    if not isinstance(is_fork, bool):  # fork flag is required, must be a real bool
        raise MalformedGitHubDataError(f"Repository {name!r} has no valid 'fork' flag")
    is_private = raw.get("private")
    if not isinstance(is_private, bool):
        raise MalformedGitHubDataError(
            f"Repository {name!r} has no valid 'private' flag"
        )
    language = raw.get("language")  # GitHub sends null when it can't detect one
    if language is not None and not isinstance(language, str):
        raise MalformedGitHubDataError(f"Repository {name!r} has an invalid 'language'")
    return Repo(
        name=name,
        language=language or None,
        is_fork=is_fork,
        is_private=is_private,
    )  # "" -> None


def repos_from_github(raw_list: Any) -> list[Repo]:
    """Convert a JSON list of repositories."""
    if not isinstance(raw_list, list):
        raise MalformedGitHubDataError("Expected a list of repositories")
    return [repo_from_github(item) for item in raw_list]


def follow_counts_from_github(raw_user: Any) -> tuple[int, int]:
    """Read (followers, following) from the /users/{name} response."""
    try:
        return _count(raw_user["followers"]), _count(raw_user["following"])
    except (KeyError, TypeError) as error:
        raise MalformedGitHubDataError("User data lacks follower counts") from error


def username_from_github(raw_user: Any) -> str:
    """Read the canonical login from a GitHub user response."""
    try:
        username = raw_user["login"]
    except (KeyError, TypeError) as error:  # also covers "user": null
        raise MalformedGitHubDataError("User data lacks a valid login") from error
    if not isinstance(username, str) or not username:
        raise MalformedGitHubDataError("User data lacks a valid login")
    return username


def build_profile(
    username: str,
    repos: list[Repo],
    commit_contributions: int = 0,
    followers: int = 0,
    following: int = 0,
) -> Profile:
    """Assemble a Profile. Anything not fetched keeps the model's default of 0/empty."""
    public_repos = [repo for repo in repos if not repo.is_private]
    non_fork_public_repos = [repo for repo in public_repos if not repo.is_fork]
    return Profile(
        username=username,
        public_repositories=len(public_repos),
        followers=followers,
        following=following,
        repository_languages=frozenset(
            repo.language for repo in non_fork_public_repos if repo.language
        ),
        commit_contributions_last_12_months=commit_contributions,
    )


def _count(value: Any) -> int:
    # bool is a subclass of int in Python, so exclude it explicitly
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MalformedGitHubDataError(f"Expected a non-negative integer, got {value!r}")
    return value
