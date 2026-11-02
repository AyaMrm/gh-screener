from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ollama import chat

from gh_screener.domain.models import ScreeningCriteria

_MODEL = "qwen2.5:3b"
_FIELDS = {
    "minimum_commit_contributions_last_12_months",
    "maximum_commit_contributions_last_12_months",
    "preferred_languages",
    "minimum_public_repositories",
    "exclude_env_committers",
}

_COMMIT_CATEGORIES = (
    (r"\blegendary\b", 2000, None),
    (r"\bhighly[\s-]+active\b", 200, None),
    (r"\bvery[\s-]+active\b", 500, None),
    (r"\bactive\b", 50, None),
    (r"\blow[\s-]+activity\b|\blow[\s-]+commit(?:s|ment)?\b", None, 49),
)
_REPOSITORY_CATEGORIES = (
    (r"\bsenior[\s-]+dev\b", 20),
    (r"\bgithub[\s-]*ceo\b", 50),
)
_NEGATION = re.compile(
    r"\b(?:not(?!\s+only)|never|without|no|don't|doesn't|didn't|"
    r"isn't|aren't|wasn't|weren't|inactive|less)\b",
    re.IGNORECASE,
)
_NUMERIC_COMMIT = re.compile(
    r"\b(?:at\s+least|more\s+than|over|at\s+most|fewer\s+than|"
    r"less\s+than|between|exactly)\s+\d+"
    r".{0,40}\b(?:commits?|contributions?)\b",
    re.IGNORECASE | re.DOTALL,
)
_NUMERIC_REPOSITORY = re.compile(
    r"\b(?:at\s+least|more\s+than|over|minimum|min|at\s+most|"
    r"fewer\s+than|less\s+than|between|exactly)\s+\d+"
    r".{0,40}\b(?:public\s+)?(?:repos?|repositories|projects)\b",
    re.IGNORECASE | re.DOTALL,
)


class CriteriaParseError(ValueError):
    """Raised when the model response cannot safely become screening criteria."""


def _is_negated(text: str, start: int) -> bool:
    """Check for a negation in the same clause immediately before a phrase."""
    prefix = text[:start]
    prefix = re.split(
        r"[,;.!?\n]|\b(?:but|however|although|whereas)\b",
        prefix,
        flags=re.IGNORECASE,
    )[-1]
    prefix = prefix[-40:]
    return _NEGATION.search(prefix) is not None


def enforce_predefined_categories(user_text: str, data: dict[str, Any]) -> dict[str, Any]:
    """Apply exact category mappings only when the request states them positively."""
    commit_match = None
    for pattern, minimum, maximum in _COMMIT_CATEGORIES:
        match = re.search(pattern, user_text, re.IGNORECASE)
        if match and not _is_negated(user_text, match.start()):
            commit_match = (minimum, maximum)
            break

    has_numeric_commit = _NUMERIC_COMMIT.search(user_text) is not None
    if commit_match is not None:
        data["minimum_commit_contributions_last_12_months"] = commit_match[0]
        data["maximum_commit_contributions_last_12_months"] = commit_match[1]
    elif not has_numeric_commit:
        # Prevent a vague or negated category from becoming an invented threshold.
        data["minimum_commit_contributions_last_12_months"] = None
        data["maximum_commit_contributions_last_12_months"] = None

    public_phrases = list(re.finditer(
        r"\bpublic\s+(?:repos?|repositories|projects|work)\b",
        user_text,
        re.IGNORECASE,
    ))
    positive_public_phrase = next(
        (
            match
            for match in public_phrases
            if not _is_negated(user_text, match.start())
        ),
        None,
    )
    has_positive_category = False
    for pattern, minimum in _REPOSITORY_CATEGORIES:
        match = re.search(pattern, user_text, re.IGNORECASE)
        if match and not _is_negated(user_text, match.start()):
            has_positive_category = True
            data["minimum_public_repositories"] = minimum
            break

    if positive_public_phrase:
        several_phrase = re.search(
            r"\bseveral\s+public\s+(?:repos?|repositories|projects)\b",
            user_text,
            re.IGNORECASE,
        )
        if several_phrase and not _is_negated(user_text, several_phrase.start()):
            data["minimum_public_repositories"] = 10
        elif not has_positive_category and not _NUMERIC_REPOSITORY.search(user_text):
            data["minimum_public_repositories"] = 1
    elif (
        not has_positive_category
        and not _NUMERIC_REPOSITORY.search(user_text)
    ):
        data["minimum_public_repositories"] = None

    return data


def _validate_response(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CriteriaParseError("Ollama returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise CriteriaParseError("Ollama response must be a JSON object.")
    if set(data) != _FIELDS:
        missing = sorted(_FIELDS - set(data))
        extra = sorted(set(data) - _FIELDS)
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        if extra:
            details.append("unexpected fields: " + ", ".join(extra))
        raise CriteriaParseError(
            "Invalid criteria fields (" + "; ".join(details) + ")."
        )

    for field in (
        "minimum_commit_contributions_last_12_months",
        "maximum_commit_contributions_last_12_months",
        "minimum_public_repositories",
    ):
        value = data[field]
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise CriteriaParseError(
                f"{field} must be a non-negative integer or null."
            )

    languages = data["preferred_languages"]
    if not isinstance(languages, list) or any(
        not isinstance(language, str) or not language.strip()
        for language in languages
    ):
        raise CriteriaParseError(
            "preferred_languages must be a list of non-empty strings."
        )
    data["preferred_languages"] = list(
        dict.fromkeys(language.strip() for language in languages)
    )

    if not isinstance(data["exclude_env_committers"], bool):
        raise CriteriaParseError("exclude_env_committers must be a boolean.")

    minimum = data["minimum_commit_contributions_last_12_months"]
    maximum = data["maximum_commit_contributions_last_12_months"]
    if minimum is not None and maximum is not None and minimum > maximum:
        raise CriteriaParseError("Minimum commit contributions cannot exceed the maximum.")
    return data


def parse_request(user_text: str) -> ScreeningCriteria:
    """Use Ollama to extract criteria, then validate and apply explicit category rules."""
    prompt_path = Path(__file__).with_name("prompt.txt")
    prompt = prompt_path.read_text(encoding="utf-8") + f"\n\nUser request:\n{user_text}"
    response = chat(
        model=_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )

    try:
        raw_response = response.message.content
    except AttributeError as exc:
        raise CriteriaParseError("Ollama returned an incomplete response.") from exc
    if not isinstance(raw_response, str):
        raise CriteriaParseError("Ollama response content must be text.")

    data = _validate_response(raw_response)
    data = enforce_predefined_categories(user_text, data)
    return ScreeningCriteria(
        minimum_commit_contributions_last_12_months=data[
            "minimum_commit_contributions_last_12_months"
        ],
        maximum_commit_contributions_last_12_months=data[
            "maximum_commit_contributions_last_12_months"
        ],
        preferred_languages=frozenset(data["preferred_languages"]),
        minimum_public_repositories=data["minimum_public_repositories"],
        exclude_env_committers=data["exclude_env_committers"],
    )
