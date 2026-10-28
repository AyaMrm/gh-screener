"""Parse raw user input into normalised GitHub usernames.

Accepted forms
--------------
* Plain username:               octocat
* Full URL (https or http):     https://github.com/octocat
* URL without scheme:           github.com/octocat
* Trailing slash is ignored:    https://github.com/octocat/

Any other value raises :class:`~gh_screener.domain.exceptions.InvalidProfileError`.
"""

from __future__ import annotations

import re

from gh_screener.domain.exceptions import InvalidProfileError

_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")


_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?github\.com/"
    r"([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/?$"
)


def parse_username(raw: str) -> str:
    """Return the GitHub username extracted from *raw*.

    Parameters
    ----------
    raw:
        A GitHub username or a GitHub profile URL supplied by the user.

    Returns
    -------
    str
        The normalised, lowercase-preserved username (GitHub usernames are
        case-insensitive but we keep the original casing from the input).

    Raises
    ------
    InvalidProfileError
        If *raw* is empty, blank, or does not match any recognised format.
    """
    value = raw.strip()

    if not value:
        raise InvalidProfileError(
            "A username or GitHub profile URL is required but an empty string was given."
        )

    url_match = _GITHUB_URL_RE.match(value)
    if url_match:
        return url_match.group(1)

    if _USERNAME_RE.match(value):
        return value

    raise InvalidProfileError(
        f"{value!r} is not a valid GitHub username or profile URL. "
        "Accepted formats: 'octocat' or 'https://github.com/octocat'."
    )
