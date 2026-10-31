
from gh_screener.model.criteria_parser import parse_request


def test_basic_screening_criteria():
    request = """
    Find Python and Java developers with at least 50 commits
    in the last year, at least 3 public repositories,
    and exclude anyone who committed .env files.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 50
    assert criteria.maximum_commit_contributions_last_12_months is None
    assert criteria.preferred_languages == frozenset({"Python", "Java"})
    assert criteria.minimum_public_repositories == 3
    assert criteria.exclude_env_committers is True


def test_experienced_python_developers():
    request = """
    I need experienced Python developers who have been
    actively contributing to GitHub over the past year.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months is None
    assert criteria.minimum_public_repositories is None
    assert criteria.preferred_languages == frozenset({"Python"})


def test_highly_active_users():
    request = "Give me a highly-active user."

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 200
    assert criteria.maximum_commit_contributions_last_12_months is None


def test_github_ceo_projects():
    request = "A user with github-ceo projects."

    criteria = parse_request(request)

    assert criteria.minimum_public_repositories == 50
    assert criteria.minimum_commit_contributions_last_12_months is None


def test_legendary_user_with_public_repos():
    request = "Give me a legendary user with public repos."

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 2000
    assert criteria.maximum_commit_contributions_last_12_months is None
    assert criteria.minimum_public_repositories == 1




def test_experienced_developers_with_public_projects():
    request = """
    I want experienced Python developers who have worked on
    several public projects.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months is None
    assert criteria.preferred_languages == frozenset({"Python"})
    assert criteria.minimum_public_repositories == 10
    assert criteria.exclude_env_committers is False


def test_active_developers_with_multiple_languages():
    request = """
    Find me active developers who know JavaScript and TypeScript
    and have at least 10 public repositories.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 50
    assert criteria.preferred_languages == frozenset({"JavaScript", "TypeScript"})
    assert criteria.minimum_public_repositories == 10


def test_legendary_developer_with_public_work():
    request = """
    I need a legendary developer, preferably someone with
    some public work on GitHub.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 2000
    assert criteria.preferred_languages == frozenset()
    assert criteria.minimum_public_repositories == 1


def test_go_developers_with_security_exclusion():
    request = """
    Look for Go developers with at least 100 contributions
    this year. Avoid anyone who accidentally exposed
    environment files in their repositories.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 100
    assert criteria.preferred_languages == frozenset({"Go"})
    assert criteria.minimum_public_repositories is None
    assert criteria.exclude_env_committers is True


def test_highly_active_senior_python_developers():
    request = """
    I'm looking for highly-active senior-dev profiles,
    ideally with Python skills.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 200
    assert criteria.preferred_languages == frozenset({"Python"})
    assert criteria.minimum_public_repositories == 20