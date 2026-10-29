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

from typing import Annotated

import typer

from gh_screener.application.screen_profiles import screen_profiles
from gh_screener.cli.parser import parse_username
from gh_screener.domain.criteria import (
    COMMIT_OPTIONS,
    OPEN_SOURCE_PROJECT_OPTIONS,
    build_criteria,
)
from gh_screener.domain.exceptions import (
    InvalidProfileError,
    UnknownCriteriaOptionError,
)

app = typer.Typer(
    name="gh-screener",
    help="Screen GitHub profiles against chosen criteria.",
    no_args_is_help=True,
)

_COMMIT_CHOICES = ", ".join(COMMIT_OPTIONS)
_PROJECT_CHOICES = ", ".join(OPEN_SOURCE_PROJECT_OPTIONS)


@app.command()
def screen(
    inputs: Annotated[
        list[str],
        typer.Argument(
            help="One or more GitHub usernames or profile URLs to screen.",
            metavar="USERNAME_OR_URL",
        ),
    ],
    commits: Annotated[
        str | None,
        typer.Option(
            "--commits",
            help=f"Commit activity filter. Choices: {_COMMIT_CHOICES}.",
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
    open_source_projects: Annotated[
        str | None,
        typer.Option(
            "--open-source-projects",
            help=f"Open-source project filter. Choices: {_PROJECT_CHOICES}.",
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
      gh-screener screen octocat torvalds --commits active
      gh-screener screen https://github.com/octocat --languages Python --languages Go
      gh-screener screen octocat --open-source-projects senior-dev
    """

    usernames: list[str] = []
    for raw in inputs:
        try:
            usernames.append(parse_username(raw))
        except InvalidProfileError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1)

    try:
        criteria = build_criteria(
            commits=commits,
            languages=languages or [],
            open_source_projects=open_source_projects,
            exclude_env_committers=exclude_env_committers,
        )
    except UnknownCriteriaOptionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    try:
        from gh_screener.config import get_github_token
        from gh_screener.infra.github_client import GitHubClient

        token = get_github_token()
        repository = GitHubClient(token=token)
    except RuntimeError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Screening {len(usernames)} profile(s)...\n")
    result = screen_profiles(usernames, criteria, repository)

    _print_section("Matched", result.matched_profiles, lambda p: p.username)
    _print_section("Rejected", result.rejected_profiles, lambda p: p.username)
    _print_error_section(result.errors)

    if result.errors:
        raise typer.Exit(code=2)


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
