"""Unit tests for application/screen_profiles.py — issue #12.

All tests use FakeProfileRepository so no network or GitHub token is needed.
"""


from gh_screener.application.screen_profiles import screen_profiles
from gh_screener.domain.criteria import build_criteria
from gh_screener.domain.models import Profile
from tests.fakes import FakeProfileRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(username: str, **kwargs) -> Profile:  # type: ignore[no-untyped-def]
    return Profile(username=username, **kwargs)


# ---------------------------------------------------------------------------
# Empty criteria — every profile passes
# ---------------------------------------------------------------------------

def test_empty_criteria_matches_every_profile() -> None:
    profiles = {
        "alice": _profile("alice"),
        "bob": _profile("bob"),
    }
    repo = FakeProfileRepository(profiles)
    result = screen_profiles(["alice", "bob"], build_criteria(), repo)

    assert [p.username for p in result.matched_profiles] == ["alice", "bob"]
    assert result.rejected_profiles == []
    assert result.errors == []


def test_secret_filter_only_scans_and_rejects_when_requested() -> None:
    profile = _profile("dev", has_committed_env_files=True)
    repo = FakeProfileRepository({"dev": profile})

    without_filter = screen_profiles(["dev"], build_criteria(), repo)

    assert [p.username for p in without_filter.matched_profiles] == ["dev"]
    assert repo.env_scan_calls == []

    with_filter = screen_profiles(
        ["dev"], build_criteria(exclude_env_committers=True), repo
    )

    assert with_filter.matched_profiles == []
    assert [p.username for p in with_filter.rejected_profiles] == ["dev"]
    assert repo.env_scan_calls == ["dev"]


# ---------------------------------------------------------------------------
# Commit criterion
# ---------------------------------------------------------------------------

def test_profile_with_enough_commits_is_matched() -> None:
    repo = FakeProfileRepository({"octocat": _profile("octocat", commits_last_12_months=100)})
    result = screen_profiles(["octocat"], build_criteria(commits="active"), repo)

    assert result.matched_profiles[0].username == "octocat"
    assert result.rejected_profiles == []


def test_profile_with_too_few_commits_is_rejected() -> None:
    repo = FakeProfileRepository({"octocat": _profile("octocat", commits_last_12_months=10)})
    result = screen_profiles(["octocat"], build_criteria(commits="active"), repo)

    assert result.rejected_profiles[0].username == "octocat"
    assert result.matched_profiles == []


def test_low_commits_criterion_rejects_high_commit_profile() -> None:
    repo = FakeProfileRepository({"octocat": _profile("octocat", commits_last_12_months=100)})
    result = screen_profiles(["octocat"], build_criteria(commits="low"), repo)

    assert result.rejected_profiles[0].username == "octocat"


# ---------------------------------------------------------------------------
# Open-source projects criterion
# ---------------------------------------------------------------------------

def test_profile_with_enough_projects_is_matched() -> None:
    repo = FakeProfileRepository({"dev": _profile("dev", public_repositories=25)})
    result = screen_profiles(["dev"], build_criteria(public_repositories="senior-dev"), repo)

    assert result.matched_profiles[0].username == "dev"


def test_profile_with_too_few_projects_is_rejected() -> None:
    repo = FakeProfileRepository({"dev": _profile("dev", public_repositories=5)})
    result = screen_profiles(["dev"], build_criteria(public_repositories="senior-dev"), repo)

    assert result.rejected_profiles[0].username == "dev"


# ---------------------------------------------------------------------------
# Language criterion
# ---------------------------------------------------------------------------

def test_profile_with_required_language_is_matched() -> None:
    repo = FakeProfileRepository({
        "pythonista": _profile(
            "pythonista",
            repository_languages=frozenset({"Python", "Go"}),
        )
    })
    result = screen_profiles(
        ["pythonista"], build_criteria(languages=["Python"]), repo
    )

    assert result.matched_profiles[0].username == "pythonista"


def test_profile_missing_required_language_is_rejected() -> None:
    repo = FakeProfileRepository({
        "jsdev": _profile("jsdev", repository_languages=frozenset({"JavaScript"}))
    })
    result = screen_profiles(["jsdev"], build_criteria(languages=["Python"]), repo)

    assert result.rejected_profiles[0].username == "jsdev"


def test_all_required_languages_must_be_present() -> None:
    # Profile has Python but not Go → rejected.
    repo = FakeProfileRepository({
        "dev": _profile("dev", repository_languages=frozenset({"Python"}))
    })
    result = screen_profiles(
        ["dev"], build_criteria(languages=["Python", "Go"]), repo
    )

    assert result.rejected_profiles[0].username == "dev"


# ---------------------------------------------------------------------------
# Combined criteria
# ---------------------------------------------------------------------------

def test_profile_must_meet_all_criteria_to_be_matched() -> None:
    # Has the language but not enough commits → rejected.
    repo = FakeProfileRepository({
        "dev": _profile(
            "dev",
            commits_last_12_months=10,
            repository_languages=frozenset({"Python"}),
        )
    })
    result = screen_profiles(
        ["dev"],
        build_criteria(commits="active", languages=["Python"]),
        repo,
    )

    assert result.rejected_profiles[0].username == "dev"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_unknown_username_produces_error_not_crash() -> None:
    repo = FakeProfileRepository({})
    result = screen_profiles(["ghost"], build_criteria(), repo)

    assert result.errors[0].username == "ghost"
    assert result.matched_profiles == []
    assert result.rejected_profiles == []


def test_error_does_not_stop_other_profiles_from_being_processed() -> None:
    repo = FakeProfileRepository({"alice": _profile("alice", commits_last_12_months=200)})
    # "ghost" doesn't exist but "alice" should still be matched.
    result = screen_profiles(
        ["ghost", "alice"], build_criteria(commits="active"), repo
    )

    assert result.errors[0].username == "ghost"
    assert result.matched_profiles[0].username == "alice"


def test_multiple_profiles_are_bucketed_independently() -> None:
    repo = FakeProfileRepository({
        "high": _profile("high", commits_last_12_months=500),
        "low": _profile("low", commits_last_12_months=1),
    })
    result = screen_profiles(
        ["high", "low"], build_criteria(commits="active"), repo
    )

    assert [p.username for p in result.matched_profiles] == ["high"]
    assert [p.username for p in result.rejected_profiles] == ["low"]
    assert result.errors == []
