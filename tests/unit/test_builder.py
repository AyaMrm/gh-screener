import pytest

from gh_screener.domain.criteria import build_criteria
from gh_screener.domain.filter.builder import build_filters
from gh_screener.domain.models import Profile


def test_no_criteria_returns_empty_list():
    criteria=build_criteria()
    filters=build_filters(criteria)
    assert filters==[]


def test_secret_filter_is_only_built_when_requested():
    assert build_filters(build_criteria()) == []

    filters = build_filters(build_criteria(exclude_env_committers=True))

    assert len(filters) == 1
    assert filters[0].requires == frozenset({"has_committed_env_files"})
    assert filters[0].matches(
        Profile(username="careful", has_committed_env_files=False)
    ) is True
    assert filters[0].matches(
        Profile(username="careless", has_committed_env_files=True)
    ) is False

@pytest.mark.parametrize(
    ("criteria","expected_count"),
    [
        (build_criteria(commit_contributions="active"), 1),
        (build_criteria(public_repositories="senior-dev"), 1),
        (build_criteria(languages=["Python"]),1),
        (
            build_criteria(
                commit_contributions="active",
                public_repositories="senior-dev",
                languages=["Python"],
            ),
            3,
        )
    ]
)
def test_build_filters_returns_one_filter_per_selected_criterion(
    criteria,expected_count

):
    filters=build_filters(criteria)
    assert len(filters)==expected_count

def test_commit_filter_matches_profile():
    criteria=build_criteria(commit_contributions="active")
    filters=build_filters(criteria)
    profile=Profile(
        username="test_user",
        commit_contributions_last_12_months=100,
    )
    assert filters[0].matches(profile) is True

def test_project_filter_matches_profile():
    criteria=build_criteria(public_repositories="senior-dev")
    filters=build_filters(criteria)
    profile=Profile(
        username="text_user",
        public_repositories=25
    )
    assert filters[0].matches(profile) is True

def test_stack_filter_matches_profile_when_all_languages_used():
    criteria=build_criteria(languages=["Python","Java"])
    filters=build_filters(criteria)
    profile=Profile(
        username="test_user",
        repository_languages=frozenset({"Python", "Java"}),
    )
    assert filters[0].matches(profile) is True

def test_stack_filter_matches_profile_when_language_missing():
    criteria=build_criteria(languages=["Python","Java"])
    filters=build_filters(criteria)
    profile=Profile(
        username="test_user",
        repository_languages=frozenset({"Python"}),
    )
    assert filters[0].matches(profile) is False

def test_filters_expose_required_fields():
    criteria=build_criteria(
        commit_contributions="active",
        public_repositories="senior-dev",
        languages=["Python"],
    )
    filters=build_filters(criteria)
    required_filters=set().union(
        *(current_filter.requires for current_filter in filters)

    )
    assert required_filters=={
        "commit_contributions_last_12_months",
        "public_repositories",
        "repository_languages"
    }
