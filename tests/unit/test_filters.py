import pytest

from gh_screener.domain.criteria import build_criteria
from gh_screener.domain.filters.commits import filter_commits
from gh_screener.domain.models import Profile


@pytest.mark.parametrize(
    ("level", "count", "expected"),
    [
        ("low", 0, True),
        ("low", 49, True),
        ("low", 50, False),
        ("active", 49, False),
        ("active", 50, True),
        ("highly-active", 199, False),
        ("highly-active", 200, True),
        ("very-active", 499, False),
        ("very-active", 500, True),
        ("legendary", 1999, False),
        ("legendary", 2000, True),
    ],
)
def test_filter_commits(level, count, expected):
    profile = Profile(
        username="test-user",
        commits_last_12_months=count,
    )
    criteria = build_criteria(commits=level)

    assert filter_commits(profile, criteria) is expected


def test_missing_commits_data_raises_error():
    profile = Profile(
        username="test-user",
        commits_last_12_months=None,
    )
    criteria = build_criteria(commits="active")

    with pytest.raises(ValueError, match="Missing commits data"):
        filter_commits(profile, criteria)
