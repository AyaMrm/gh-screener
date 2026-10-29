
from gh_screener.domain.models import Profile, ScreeningCriteria


def filter_stack(
    profile: Profile,
    criteria: ScreeningCriteria,
) -> bool:
    profile_languages = {language.casefold() for language in profile.repository_languages}
    required_languages = {
        language.casefold() for language in criteria.preferred_languages
    }
    return required_languages.issubset(profile_languages)
