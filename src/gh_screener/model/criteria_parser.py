
import json
import re
from pathlib import Path

from ollama import chat

from gh_screener.domain.models import ScreeningCriteria


def enforce_predefined_categories(
    user_text: str,
    data: dict,
) -> dict:
    """
    Enforce exact values for predefined screening categories.
    """

    # COMMIT ACTIVITY CATEGORIES
    commit_categories = [
        (r"\blegendary\b", 2000, None),
        (r"\bhighly[\s-]+active\b", 200, None),
        (r"\bvery[\s-]+active\b", 500, None),
        (r"\bactive\b", 50, None),
        (r"\blow\b", None, 49),
    ]

    for pattern, minimum, maximum in commit_categories:
        if re.search(pattern, user_text, re.IGNORECASE):
            data["minimum_commit_contributions_last_12_months"] = minimum
            data["maximum_commit_contributions_last_12_months"] = maximum
            break

    has_commit_category = any(
        re.search(pattern, user_text, re.IGNORECASE)
        for pattern, _, _ in commit_categories
    )

    has_commit_number = re.search(
        r"\b(?:at least|more than|over|at most|fewer than|"
        r"less than|between|exactly)\s+\d+"
        r".{0,30}\b(?:commits?|contributions?)\b",
        user_text,
        re.IGNORECASE,
    )

    if not has_commit_category and not has_commit_number:
        data["minimum_commit_contributions_last_12_months"] = None
        data["maximum_commit_contributions_last_12_months"] = None

    # PUBLIC REPOSITORY CATEGORIES
    repository_categories = [
        (r"\bsenior[\s-]+dev\b", 20),
        (r"\bgithub\s*-\s*ceo\b|\bgithub[\s]+ceo\b|\bgithubceo\b", 50),
    ]

    for pattern, minimum in repository_categories:
        if re.search(pattern, user_text, re.IGNORECASE):
            data["minimum_public_repositories"] = minimum
            break

    # GENERIC MENTION OF PUBLIC REPOSITORIES
    mentions_public_repos = re.search(
        r"\bpublic\s+(?:repos?|repositories|projects)\b",
        user_text,
        re.IGNORECASE,
    )

    mentions_repo_category = any(
        re.search(pattern, user_text, re.IGNORECASE)
        for pattern, _ in repository_categories
    )

    # SPECIAL CASE: SEVERAL PUBLIC PROJECTS
    several_projects = re.search(
        r"\bseveral\s+public\s+(?:repos?|repositories|projects)\b",
        user_text,
        re.IGNORECASE,
    )

    if several_projects:
        data["minimum_public_repositories"] = 10

    # GENERIC MENTION OF PUBLIC REPOSITORIES
    elif mentions_public_repos and not mentions_repo_category:
        has_repo_number = re.search(
            r"\b(?:at least|more than|over|minimum|min)\s+\d+"
            r".{0,30}\b(?:public\s+)?(?:repos?|repositories)\b",
            user_text,
            re.IGNORECASE,
        )

        if not has_repo_number:
            data["minimum_public_repositories"] = 1

    return data


def parse_request(user_text: str) -> ScreeningCriteria:
    PROMPT_PATH = Path(__file__).with_name("prompt.txt")

    def load_prompt() -> str:
        return PROMPT_PATH.read_text(encoding="utf-8")

    prompt = load_prompt() + f"""

    User request:
    {user_text}
    """

    response = chat(
        model="qwen2.5:3b",
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )


    data = json.loads(response.message.content)
    data = enforce_predefined_categories(user_text, data)

    return ScreeningCriteria(
        minimum_commit_contributions_last_12_months=data.get(
            "minimum_commit_contributions_last_12_months"
        ),
        maximum_commit_contributions_last_12_months=data.get(
            "maximum_commit_contributions_last_12_months"
        ),
        preferred_languages=frozenset(
            language.strip()
            for language in data.get("preferred_languages", [])
            if isinstance(language, str) and language.strip()
        ),
        minimum_public_repositories=data.get(
            "minimum_public_repositories"
        ),
        exclude_env_committers=data.get(
            "exclude_env_committers", False
        ),
    )
