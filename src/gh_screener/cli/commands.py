"""CLI commands — issue #13.

Defines the ``screen`` Typer command that is the user-facing entry point for
the tool.  The command:

1. Parses each raw username / URL argument with :func:`~gh_screener.cli.parser.parse_username`.
2. Builds a :class:`~gh_screener.domain.models.ScreeningCriteria` via
   :func:`~gh_screener.domain.criteria.build_criteria`.
3. Constructs a ``GitHubClient`` (Part A) using the token from :mod:`gh_screener.config`.
4. Delegates to :func:`~gh_screener.application.screen_profiles.screen_profiles`.
5. Prints a structured summary to stdout.

Dependency rule
---------------
``cli`` may import from ``application`` and ``domain``.
The ``infra`` import (``GitHubClient``) is deferred to runtime so that the
module can still be imported and unit-tested before Part A is merged.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Annotated

import typer

from gh_screener.cli.parser import parse_username
from gh_screener.domain.criteria import (
    COMMIT_OPTIONS,
    PUBLIC_REPOSITORY_OPTIONS,
    build_criteria,
)
from gh_screener.domain.exceptions import (
    InvalidProfileError,
    UnknownCriteriaOptionError,
)
from gh_screener.domain.models import (
    ScreeningCriteria,
    ScreeningError,
    ScreeningResult,
)
from gh_screener.domain.ports import ProfileRepository

_COMMIT_CHOICES = ", ".join(COMMIT_OPTIONS)
_PROJECT_CHOICES = ", ".join(PUBLIC_REPOSITORY_OPTIONS)


def create_app(
    screening_use_case: Callable[
        [Iterable[str], ScreeningCriteria, ProfileRepository], ScreeningResult
    ],
    repository_factory: Callable[[], ProfileRepository],
) -> typer.Typer:
    """Build the CLI around the use case and repository supplied by main."""
    app = typer.Typer(
        name="gh-screener",
        help="Screen GitHub profiles against chosen criteria.",
        no_args_is_help=True,
    )

    @app.command()
    def screen(
        inputs: Annotated[
            list[str],
            typer.Argument(
                help="One or more GitHub usernames or profile URLs to screen.",
                metavar="USERNAME_OR_URL",
            ),
        ],
        commit_contributions: Annotated[
            str | None,
            typer.Option(
                "--commit-contributions",
                "--commits",
                help=(
                    "GitHub-recognized commit contribution filter over the last 365 days. "
                    f"Choices: {_COMMIT_CHOICES}."
                ),
                metavar="LEVEL",
            ),
        ] = None,
        languages: Annotated[
            list[str] | None,
            typer.Option(
                "--languages",
                help=(
                    "Required programming language (repeat the flag for multiple). "
                    "Example: --languages Python --languages Go"
                ),
                metavar="LANG",
            ),
        ] = None,
        public_repositories: Annotated[
            str | None,
            typer.Option(
                "--public-repositories",
                help=f"Public repository filter. Choices: {_PROJECT_CHOICES}.",
                metavar="LEVEL",
            ),
        ] = None,
        exclude_env_committers: Annotated[
            bool,
            typer.Option(
                "--exclude-env-committers",
                help="Reject profiles that have committed .env files.",
            ),
        ] = False,
    ) -> None:
        """Screen one or more GitHub profiles against chosen criteria.

    \b
    Examples
    --------
      gh-screener octocat torvalds --commit-contributions active
      gh-screener https://github.com/octocat --languages Python --languages Go
      gh-screener octocat --public-repositories senior-dev
        """
        usernames: list[str] = []
        input_errors: list[ScreeningError] = []
        for raw in inputs:
            try:
                usernames.append(parse_username(raw))
            except InvalidProfileError as exc:
                input_errors.append(ScreeningError(username=raw, message=str(exc)))

        if not usernames:
            _print_error_section(input_errors)
            raise typer.Exit(code=1)

        try:
            criteria = build_criteria(
                commit_contributions=commit_contributions,
                languages=languages or [],
                public_repositories=public_repositories,
                exclude_env_committers=exclude_env_committers,
            )
        except UnknownCriteriaOptionError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)

        try:
            repository = repository_factory()
        except RuntimeError as exc:
            typer.echo(f"Configuration error: {exc}", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Screening {len(usernames)} valid profile(s)...\n")
        try:
            result = screening_use_case(usernames, criteria, repository)
        finally:
            repository.close()
        result.errors[:0] = input_errors

        _print_section("Matched", result.matched_profiles, lambda p: p.username)
        _print_section("Rejected", result.rejected_profiles, lambda p: p.username)
        _print_error_section(result.errors)

        if input_errors or result.errors:
            raise typer.Exit(code=2)

    return app


def _print_section(title: str, items: list, label_fn) -> None:
    count = len(items)
    typer.echo(f"{title} ({count}):")
    if items:
        for item in items:
            typer.echo(f"  {label_fn(item)}")
    else:
        typer.echo("  (none)")
    typer.echo("")


def _print_error_section(errors: list) -> None:
    if not errors:
        return
    typer.echo(f"Errors ({len(errors)}):")
    for error in errors:
        typer.echo(f"  {error.username}: {error.message}")
    typer.echo("")
