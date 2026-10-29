"""Configuration helpers — token loading and environment setup."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get_github_token() -> str:
    """Return the GitHub personal access token from the environment.

    The token is read from the ``GITHUB_TOKEN`` environment variable, which
    can be set via a ``.env`` file (see ``.env.example``).

    Raises
    ------
    RuntimeError
        If the variable is absent or blank.
    """
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. "
            "Copy .env.example to .env and add your GitHub personal access token."
        )
    return token
