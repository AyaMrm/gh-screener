"""Application entry point: assemble the CLI, use case, and GitHub client."""

from __future__ import annotations

from gh_screener.application.screen_profiles import screen_profiles
from gh_screener.cli.commands import create_app
from gh_screener.domain.ports import ProfileRepository


def _repository_factory() -> ProfileRepository:
    """Build the GitHub adapter only when a screening command is run."""
    # Keep the concrete infrastructure dependency at the composition root.
    from gh_screener.config import get_github_token
    from gh_screener.infra.github_client import GitHubClient

    return GitHubClient(get_github_token())


app = create_app(screen_profiles, _repository_factory)


if __name__ == "__main__":
    app()
