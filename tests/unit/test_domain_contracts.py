from gh_screener.domain.criteria import ScreeningCriteria
from gh_screener.domain.filters import Filter, matches_all
from gh_screener.domain.models import Profile


class MinimumCommitsFilter(Filter):
    @property
    def requires(self) -> frozenset[str]:
        return frozenset({"commit_count"})

    def matches(self, profile: Profile) -> bool:
        return profile.commit_count >= 10


def test_screening_criteria_is_available_from_criteria_module() -> None:
    criteria = ScreeningCriteria(minimum_commits=10)

    assert criteria.minimum_commits == 10


def test_filter_declares_required_profile_data() -> None:
    profile = Profile(username="octocat", commit_count=10)
    current_filter = MinimumCommitsFilter()

    assert current_filter.requires == frozenset({"commit_count"})
    assert matches_all(profile, [current_filter])


def test_matches_all_requires_every_filter_to_match() -> None:
    profile = Profile(username="octocat", commit_count=9)
    current_filter = MinimumCommitsFilter()

    assert not matches_all(profile, [current_filter])
