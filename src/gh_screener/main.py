"""Entry point for the gh-screener CLI tool.

Declared in pyproject.toml as:
    [project.scripts]
    gh-screener = "gh_screener.main:app"

This module assembles the application: it imports the Typer app from the CLI
layer and exposes it as ``app`` so the console script can find it.
"""

from gh_screener.cli.commands import app

__all__ = ["app"]

if __name__ == "__main__":
    app()
