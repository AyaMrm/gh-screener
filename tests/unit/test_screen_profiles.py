"""Unit tests for application/screen_profiles.py — issue #12.

All tests use FakeProfileRepository so no network or GitHub token is needed.
"""

import datetime
from threading import Barrier, Event, Lock

from gh_screener.application.screen_profiles import screen_profiles
from gh_screener.domain.criteria import build_criteria
from gh_screener.domain.exceptions import RateLimitError
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
    repo = FakeProfileRepository({"octocat": _profile("octocat", commit_contributions_last_12_months=100)})
    result = screen_profiles(["octocat"], build_criteria(commit_contributions="active"), repo)

    assert result.matched_profiles[0].username == "octocat"
    assert result.rejected_profiles == []


def test_profile_with_too_few_commits_is_rejected() -> None:
    repo = FakeProfileRepository({"octocat": _profile("octocat", commit_contributions_last_12_months=10)})
    result = screen_profiles(["octocat"], build_criteria(commit_contributions="active"), repo)

    assert result.rejected_profiles[0].username == "octocat"
    assert result.matched_profiles == []


def test_low_commits_criterion_rejects_high_commit_profile() -> None:
    repo = FakeProfileRepository({"octocat": _profile("octocat", commit_contributions_last_12_months=100)})
    result = screen_profiles(["octocat"], build_criteria(commit_contributions="low"), repo)

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
            commit_contributions_last_12_months=10,
            repository_languages=frozenset({"Python"}),
        )
    })
    result = screen_profiles(
        ["dev"],
        build_criteria(commit_contributions="active", languages=["Python"]),
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
    repo = FakeProfileRepository({"alice": _profile("alice", commit_contributions_last_12_months=200)})
    # "ghost" doesn't exist but "alice" should still be matched.
    result = screen_profiles(
        ["ghost", "alice"], build_criteria(commit_contributions="active"), repo
    )

    assert result.errors[0].username == "ghost"
    assert result.matched_profiles[0].username == "alice"


def test_screening_runs_at_most_three_profiles_at_once() -> None:
    start_together = Barrier(3, timeout=3)
    lock = Lock()
    active = 0
    maximum_active = 0

    class ConcurrentRepository:
        def get_profile(self, username: str) -> Profile:
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            try:
                start_together.wait()
                return _profile(username)
            finally:
                with lock:
                    active -= 1

    usernames = ["one", "two", "three", "four", "five", "six"]
    result = screen_profiles(usernames, build_criteria(), ConcurrentRepository())

    assert maximum_active == 3
    assert [profile.username for profile in result.matched_profiles] == usernames


def test_screening_keeps_input_order_when_profiles_finish_out_of_order() -> None:
    third_finished = Event()
    completion_order: list[str] = []

    class OutOfOrderRepository:
        def get_profile(self, username: str) -> Profile:
            if username == "alice":
                assert third_finished.wait(timeout=3)
            if username == "charlie":
                completion_order.append(username)
                third_finished.set()
            else:
                completion_order.append(username)
            return _profile(username)

    usernames = ["alice", "bob", "charlie"]
    result = screen_profiles(usernames, build_criteria(), OutOfOrderRepository())

    assert completion_order.index("charlie") < completion_order.index("alice")
    assert [profile.username for profile in result.matched_profiles] == usernames


def test_rate_limit_stops_later_batches_and_marks_them_unprocessed() -> None:
    reset_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)

    class RateLimitedRepository:
        def __init__(self) -> None:
            self.profile_calls: list[str] = []

        def get_profile(self, username: str) -> Profile:
            self.profile_calls.append(username)
            if username == "bob":
                raise RateLimitError(reset_at=reset_at)
            return _profile(username)

    repository = RateLimitedRepository()
    result = screen_profiles(
        ["alice", "bob", "charlie", "dana", "erin"], build_criteria(), repository
    )

    assert set(repository.profile_calls) == {"alice", "bob", "charlie"}
    assert [profile.username for profile in result.matched_profiles] == [
        "alice",
        "charlie",
    ]
    assert result.errors[0].username == "bob"
    assert reset_at.isoformat() in result.errors[0].message
    assert [error.username for error in result.errors[1:]] == ["dana", "erin"]
    assert "Not processed" in result.errors[1].message


def test_multiple_profiles_are_bucketed_independently() -> None:
    repo = FakeProfileRepository({
        "high": _profile("high", commit_contributions_last_12_months=500),
        "low": _profile("low", commit_contributions_last_12_months=1),
    })
    result = screen_profiles(
        ["high", "low"], build_criteria(commit_contributions="active"), repo
    )

    assert [p.username for p in result.matched_profiles] == ["high"]
    assert [p.username for p in result.rejected_profiles] == ["low"]
    assert result.errors == []
