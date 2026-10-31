
import json
from types import SimpleNamespace

from gh_screener.model import criteria_parser
from gh_screener.model.criteria_parser import parse_request


def mock_ollama(monkeypatch, response_data):
    """Simulate an Ollama response without calling the actual model."""
    fake_response = SimpleNamespace(
        message=SimpleNamespace(
            content=json.dumps(response_data)
        )
    )

    monkeypatch.setattr(
        criteria_parser,
        "chat",
        lambda **kwargs: fake_response
    )


def test_basic_screening_criteria(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": 50,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": ["Python", "Java"],
        "minimum_public_repositories": 3,
        "exclude_env_committers": True
    })

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


def test_experienced_python_developers(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": None,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": ["Python"],
        "minimum_public_repositories": None,
        "exclude_env_committers": False
    })

    request = """
    I need experienced Python developers who have been
    actively contributing to GitHub over the past year.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months is None
    assert criteria.minimum_public_repositories is None
    assert criteria.preferred_languages == frozenset({"Python"})


def test_highly_active_users(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": 200,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": [],
        "minimum_public_repositories": None,
        "exclude_env_committers": False
    })

    request = "Give me a highly-active user."

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 200
    assert criteria.maximum_commit_contributions_last_12_months is None


def test_github_ceo_projects(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": None,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": [],
        "minimum_public_repositories": 50,
        "exclude_env_committers": False
    })

    request = "A user with github-ceo projects."

    criteria = parse_request(request)

    assert criteria.minimum_public_repositories == 50
    assert criteria.minimum_commit_contributions_last_12_months is None


def test_legendary_user_with_public_repos(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": 2000,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": [],
        "minimum_public_repositories": 1,
        "exclude_env_committers": False
    })

    request = "Give me a legendary user with public repos."

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 2000
    assert criteria.maximum_commit_contributions_last_12_months is None
    assert criteria.minimum_public_repositories == 1


def test_experienced_developers_with_public_projects(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": None,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": ["Python"],
        "minimum_public_repositories": 10,
        "exclude_env_committers": False
    })

    request = """
    I want experienced Python developers who have worked on
    several public projects.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months is None
    assert criteria.preferred_languages == frozenset({"Python"})
    assert criteria.minimum_public_repositories == 10
    assert criteria.exclude_env_committers is False


def test_active_developers_with_multiple_languages(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": 50,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": ["JavaScript", "TypeScript"],
        "minimum_public_repositories": 10,
        "exclude_env_committers": False
    })

    request = """
    Find me active developers who know JavaScript and TypeScript
    and have at least 10 public repositories.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 50
    assert criteria.preferred_languages == frozenset(
        {"JavaScript", "TypeScript"}
    )
    assert criteria.minimum_public_repositories == 10


def test_legendary_developer_with_public_work(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": 2000,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": [],
        "minimum_public_repositories": 1,
        "exclude_env_committers": False
    })

    request = """
    I need a legendary developer, preferably someone with
    some public work on GitHub.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 2000
    assert criteria.preferred_languages == frozenset()
    assert criteria.minimum_public_repositories == 1


def test_go_developers_with_security_exclusion(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": 100,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": ["Go"],
        "minimum_public_repositories": None,
        "exclude_env_committers": True
    })

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


def test_highly_active_senior_python_developers(monkeypatch):
    mock_ollama(monkeypatch, {
        "minimum_commit_contributions_last_12_months": 200,
        "maximum_commit_contributions_last_12_months": None,
        "preferred_languages": ["Python"],
        "minimum_public_repositories": 20,
        "exclude_env_committers": False
    })

    request = """
    I'm looking for highly-active senior-dev profiles,
    ideally with Python skills.
    """

    criteria = parse_request(request)

    assert criteria.minimum_commit_contributions_last_12_months == 200
    assert criteria.preferred_languages == frozenset({"Python"})
    assert criteria.minimum_public_repositories == 20
