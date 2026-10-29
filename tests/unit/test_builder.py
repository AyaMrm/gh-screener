import pytest
from gh_screener.domain.criteria import build_criteria
from gh_screener.domain.filter.builder import build_filters
from gh_screener.domain.models import Profile, Repo


def test_no_criteria_returns_empty_list():
    criteria=build_criteria()
    filters=build_filters(criteria)
    assert filters==[]

@pytest.mark.parametrize(
    ("criteria","expected_count"),
    [
        (build_criteria(commits="active"), 1),
        (build_criteria(open_source_projects="senior-dev"), 1),
        (build_criteria(languages=["Python"]),1),
        (
            build_criteria(
                commits="active",
                open_source_projects="senior-dev",
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
    criteria=build_criteria(commits="active")
    filters=build_filters(criteria)
    profile=Profile(
        username="test_user",
        commits_last_12_months=100,
    )
    assert filters[0].matches(profile) is True

def test_project_filter_matches_profile():
    criteria=build_criteria(open_source_projects="senior-dev")
    filters=build_filters(criteria)
    profile=Profile(
        username="text_user",
        open_source_projects=25
    )
    assert filters[0].matches(profile) is True

def test_stack_filter_matches_profile_when_all_languages_used():
    criteria=build_criteria(languages=["Python","Java"])
    repos=[
        Repo(name="repo-1",language="Python",is_fork=False),
        Repo(name="repo-2",language="Java",is_fork=False),

    ]
    filters=build_filters(criteria,repos)
    profile=Profile(username="test_user")
    assert filters[0].matches(profile) is True

def test_stack_filter_matches_profile_when_language_missing():
    criteria=build_criteria(languages=["Python","Java"])
    repos=[
            Repo(name="repo-1",language="Python",is_fork=False),
    
    ]
    filters=build_filters(criteria,repos)
    profile=Profile(username="test_user")
    assert filters[0].matches(profile) is False

def test_filters_expose_required_fields():
    criteria=build_criteria(
        commits="active",
        open_source_projects="senior-dev",
        languages=["Python"],
    )
    repos =[
        Repo(name="repo-1",language="Python",is_fork=False),
    ]
    filters=build_filters(criteria,repos)
    required_filters=set().union(
        *(current_filter.requires for current_filter in filters)

    )
    assert required_filters=={
        "commits_last_12_months",
        "open_source_projects",
        "repos"
    }