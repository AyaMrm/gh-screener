


from __future__ import annotations

from typer.testing import CliRunner

from gh_screener.domain.models import Profile
from gh_screener.main import app
from tests.fakes import FakeProfileRepository

runner = CliRunner()




def _profile(username: str, **kwargs) -> Profile:  # type: ignore[no-untyped-def]
    return Profile(username=username, **kwargs)


def _invoke(monkeypatch, profiles: dict, args: list[str]):  # type: ignore[no-untyped-def]

    repo = FakeProfileRepository(profiles)

    import gh_screener.config as config_module
    import gh_screener.infra.github_client as client_module

    monkeypatch.setattr(config_module, "get_github_token", lambda: "fake-token")
    monkeypatch.setattr(client_module, "GitHubClient", lambda token: repo)

    return runner.invoke(app, args, catch_exceptions=False)


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------

def test_screen_prints_matched_username(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _invoke(
        monkeypatch,
        {"octocat": _profile("octocat")},
        ["octocat"],
    )

    assert result.exit_code == 0
    assert "octocat" in result.output


def test_screen_shows_matched_section(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _invoke(
        monkeypatch,
        {"alice": _profile("alice", commits_last_12_months=100)},
        ["alice", "--commits", "active"],
    )

    assert result.exit_code == 0
    assert "Matched" in result.output
    assert "alice" in result.output


def test_screen_shows_rejected_section(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _invoke(
        monkeypatch,
        {"bob": _profile("bob", commits_last_12_months=5)},
        ["bob", "--commits", "active"],
    )

    assert result.exit_code == 0
    assert "Rejected" in result.output
    assert "bob" in result.output





def test_screen_multiple_usernames(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    profiles = {
        "alice": _profile("alice", commits_last_12_months=200),
        "bob": _profile("bob", commits_last_12_months=10),
    }
    result = _invoke(monkeypatch, profiles, ["alice", "bob", "--commits", "active"])

    assert result.exit_code == 0
    assert "alice" in result.output
    assert "bob" in result.output



def test_screen_accepts_github_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _invoke(
        monkeypatch,
        {"octocat": _profile("octocat")},
        ["https://github.com/octocat"],
    )

    assert result.exit_code == 0
    assert "octocat" in result.output




def test_invalid_username_exits_with_code_1(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _invoke(monkeypatch, {}, ["not a url or username!"])

    assert result.exit_code == 1


def test_unknown_commit_option_exits_with_code_1(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    result = _invoke(
        monkeypatch,
        {"octocat": _profile("octocat")},
        ["octocat", "--commits", "turbo-super-active"],
    )

    assert result.exit_code == 1




def test_unknown_user_produces_error_and_exit_code_2(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # FakeProfileRepository raises ProfileNotFoundError for unknown users.
    result = _invoke(monkeypatch, {}, ["ghost"])

    assert result.exit_code == 2
    assert "ghost" in result.output


def test_error_does_not_block_other_users(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    profiles = {"alice": _profile("alice", commits_last_12_months=100)}
    # "ghost" is not in the repo → error; "alice" should still appear matched.
    result = _invoke(
        monkeypatch,
        profiles,
        ["ghost", "alice", "--commits", "active"],
    )

    assert result.exit_code == 2
    assert "alice" in result.output


# ---------------------------------------------------------------------------
# Language filter
# ---------------------------------------------------------------------------

def test_language_filter_works_via_cli(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    profiles = {
        "pythonista": _profile("pythonista", repository_languages=frozenset({"Python"})),
        "jsdev": _profile("jsdev", repository_languages=frozenset({"JavaScript"})),
    }
    result = _invoke(
        monkeypatch,
        profiles,
        ["pythonista", "jsdev", "--languages", "Python"],
    )

    assert result.exit_code == 0
    assert "pythonista" in result.output
    assert "jsdev" in result.output  # jsdev appears in Rejected section




def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [], catch_exceptions=False)

    # Typer with no_args_is_help=True shows the help text.
    # The output should mention the command or its options.
    assert any(
        word in result.output.lower()
        for word in ("screen", "usage", "gh-screener", "username")
    )
