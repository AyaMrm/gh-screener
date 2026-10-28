#test both commits and stack

import pytest

from gh_screener.domain.criteria import build_criteria
from gh_screener.domain.filter.commits import filter_commits
from gh_screener.domain.filter.stack import filter_stack
from gh_screener.domain.models import Profile, Repo, ScreeningCriteria

# -------------------------
# Commits tests
# -------------------------

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


# -------------------------
# Stack language tests
# -------------------------

def make_repo(
    language: str | None,
    is_fork: bool = False,
) -> Repo:
    return Repo(
        name="test-repo",
        language=language,
        is_fork=is_fork,
    )


def make_profile() -> Profile:
    return Profile(username="test-user")


def test_matches_when_all_preferred_languages_are_used():
    repos = [
        make_repo("Python"),
        make_repo("Dart"),
        make_repo("Java"),
    ]
    profile = make_profile()
    criteria = ScreeningCriteria(
        preferred_languages=frozenset({"Python", "Dart"})
    )

    assert filter_stack(repos, profile, criteria) is True


def test_rejects_when_a_preferred_language_is_missing():
    repos = [
        make_repo("Python"),
        make_repo("Java"),
    ]
    profile = make_profile()
    criteria = ScreeningCriteria(
        preferred_languages=frozenset({"Python", "Dart"})
    )

    assert filter_stack(repos, profile, criteria) is False


def test_language_matching_is_case_insensitive():
    repos = [make_repo("python")]
    profile = make_profile()
    criteria = ScreeningCriteria(
        preferred_languages=frozenset({"Python"})
    )

    assert filter_stack(repos, profile, criteria) is True


def test_ignores_forked_repositories():
    repos = [
        make_repo("Python"),
        make_repo("Dart", is_fork=True),
    ]
    profile = make_profile()
    criteria = ScreeningCriteria(
        preferred_languages=frozenset({"Python", "Dart"})
    )

    assert filter_stack(repos, profile, criteria) is False


def test_ignores_repositories_without_a_language():
    repos = [
        make_repo(None),
        make_repo("Python"),
    ]
    profile = make_profile()
    criteria = ScreeningCriteria(
        preferred_languages=frozenset({"Python"})
    )

    assert filter_stack(repos, profile, criteria) is True


def test_empty_preferred_languages_match_any_profile():
    repos = [make_repo("Python")]
    profile = make_profile()
    criteria = ScreeningCriteria()

    assert filter_stack(repos, profile, criteria) is True


def test_rejects_when_no_repositories_use_the_preferred_language():
    repos = []
    profile = make_profile()
    criteria = ScreeningCriteria(
        preferred_languages=frozenset({"Python"})
    )

    assert filter_stack(repos, profile, criteria) is False


# -------------------------
# Optional interactive menu
# -------------------------

def main():
    print("Which tests do you want to run?")
    print("1. Commits")
    print("2. Stack languages")
    print("3. Both")

    choice = input("Enter 1, 2, or 3: ").strip()

    if choice == "1":
        test_files = ["tests/unit/test_filters.py"]
        pytest.main(["-k", "commits", *test_files])

    elif choice == "2":
        pytest.main(["-k", "stack", "tests/unit/test_filters.py"])

    elif choice == "3":
        pytest.main(["tests/unit/test_filters.py"])

    else:
        print("Invalid choice. Please enter 1, 2, or 3.")


if __name__ == "__main__":
    main()
