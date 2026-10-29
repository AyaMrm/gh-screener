from gh_screener.domain.models import Profile, ScreeningCriteria


#if the profile committed .env files -> false
def filter_secrets(profile: Profile, criteria: ScreeningCriteria) -> bool:
    return not profile.has_committed_env_files