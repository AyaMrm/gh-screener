"""Unit tests for cli/parser.py — issue #4."""

import pytest

from gh_screener.cli.parser import parse_username
from gh_screener.domain.exceptions import InvalidProfileError

# ---------------------------------------------------------------------------
# Valid plain usernames
# ---------------------------------------------------------------------------

def test_plain_username_is_returned_unchanged() -> None:
    assert parse_username("octocat") == "octocat"


def test_single_character_username() -> None:
    assert parse_username("a") == "a"


def test_username_with_hyphens() -> None:
    assert parse_username("my-cool-username") == "my-cool-username"


def test_leading_and_trailing_whitespace_is_stripped() -> None:
    assert parse_username("  octocat  ") == "octocat"


# ---------------------------------------------------------------------------
# Valid GitHub URLs
# ---------------------------------------------------------------------------

def test_https_url() -> None:
    assert parse_username("https://github.com/octocat") == "octocat"


def test_http_url() -> None:
    assert parse_username("http://github.com/octocat") == "octocat"


def test_url_without_scheme() -> None:
    assert parse_username("github.com/octocat") == "octocat"


def test_url_with_trailing_slash() -> None:
    assert parse_username("https://github.com/octocat/") == "octocat"


def test_url_with_whitespace() -> None:
    assert parse_username("  https://github.com/octocat  ") == "octocat"


# ---------------------------------------------------------------------------
# Invalid inputs — must raise InvalidProfileError
# ---------------------------------------------------------------------------

def test_empty_string_raises() -> None:
    with pytest.raises(InvalidProfileError):
        parse_username("")


def test_blank_string_raises() -> None:
    with pytest.raises(InvalidProfileError):
        parse_username("   ")


def test_username_starting_with_hyphen_raises() -> None:
    with pytest.raises(InvalidProfileError):
        parse_username("-invalid")


def test_username_ending_with_hyphen_raises() -> None:
    with pytest.raises(InvalidProfileError):
        parse_username("invalid-")


def test_arbitrary_string_raises() -> None:
    with pytest.raises(InvalidProfileError):
        parse_username("not a url or username!")


def test_url_with_path_beyond_username_raises() -> None:
    # Only profile root URLs are accepted — repo or sub-paths are not.
    with pytest.raises(InvalidProfileError):
        parse_username("https://github.com/octocat/some-repo")
