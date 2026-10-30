import pytest

from gh_screener.domain.criteria import (
    COMMIT_OPTIONS,
    PUBLIC_REPOSITORY_OPTIONS,
    ScreeningCriteria,
    build_criteria,
)
from gh_screener.domain.exceptions import UnknownCriteriaOptionError
from gh_screener.domain.filters import Filter, matches_all
from gh_screener.domain.models import Profile


class MinimumCommitsFilter(Filter):
    @property
    def requires(self) -> frozenset[str]:
        return frozenset({"commit_contributions_last_12_months"})

    def matches(self, profile: Profile) -> bool:
        return profile.commit_contributions_last_12_months >= 10


def test_screening_criteria_is_available_from_criteria_module() -> None:
    criteria = ScreeningCriteria(minimum_commit_contributions_last_12_months=10)

    assert criteria.minimum_commit_contributions_last_12_months == 10
    assert not criteria.is_empty


def test_criteria_is_empty_when_no_option_is_selected() -> None:
    assert build_criteria().is_empty


def test_predefined_options_are_kept_in_one_place() -> None:
    assert COMMIT_OPTIONS == {
        "low": {"maximum": 49},
        "active": {"minimum": 50},
        "highly-active": {"minimum": 200},
        "very-active": {"minimum": 500},
        "legendary": {"minimum": 2_000},
    }
    assert PUBLIC_REPOSITORY_OPTIONS == {
        "senior-dev": 20,
        "github-ceo": 50,
    }


def test_build_criteria_translates_selected_options() -> None:
    criteria = build_criteria(
        commit_contributions="low",
        languages=[" Python ", "Go"],
        public_repositories="senior-dev",
    )

    assert criteria.minimum_commit_contributions_last_12_months is None
    assert criteria.maximum_commit_contributions_last_12_months == 49
    assert criteria.preferred_languages == frozenset({"Python", "Go"})
    assert criteria.minimum_public_repositories == 20


@pytest.mark.parametrize(
    ("kwargs", "option_name"),
    [
        ({"commit_contributions": "unknown"}, "commit contributions"),
        ({"public_repositories": "unknown"}, "public repositories"),
    ],
)
def test_unknown_option_gives_a_clear_error(
    kwargs: dict[str, str], option_name: str
) -> None:
    with pytest.raises(
        UnknownCriteriaOptionError,
        match=rf"Unknown {option_name} option 'unknown'. Choose one of:",
    ):
        build_criteria(**kwargs)


def test_filter_declares_required_profile_data() -> None:
    profile = Profile(username="octocat", commit_contributions_last_12_months=10)
    current_filter = MinimumCommitsFilter()

    assert current_filter.requires == frozenset({"commit_contributions_last_12_months"})
    assert matches_all(profile, [current_filter])


def test_matches_all_requires_every_filter_to_match() -> None:
    profile = Profile(username="octocat", commit_contributions_last_12_months=9)
    current_filter = MinimumCommitsFilter()

    assert not matches_all(profile, [current_filter])
