class DomainError(Exception):
    """Base class for expected domain errors."""


class InvalidProfileError(DomainError):
    """Raised when a profile identifier cannot be used."""


class ProfileNotFoundError(DomainError):
    """Raised when GitHub has no profile for the requested username."""


class UnknownCriteriaOptionError(DomainError):
    """Raised when a user selects an unsupported criteria option."""
    

class GitHubIntegrationError(DomainError):
    """Base class for failures that originate from talking to GitHub."""


class InvalidUsernameError(GitHubIntegrationError, ProfileNotFoundError):
    """Raised when GitHub has no user for the requested username (HTTP 404)."""


class RateLimitError(GitHubIntegrationError):
    """Raised when the GitHub API rate limit is exceeded (HTTP 403/429)."""

    def __init__(self, message="GitHub API rate limit exceeded", reset_at=None, remaining=0):
        self.reset_at = reset_at
        self.remaining = remaining
        super().__init__(message)


class AuthenticationError(GitHubIntegrationError):
    """Raised when the GitHub token is missing, invalid, or lacks permission."""

    def __init__(self, message="GitHub authentication failed", status_code=401):
        # Note: deliberately never accepts or stores the token itself.
        self.status_code = status_code
        super().__init__(message)


class GitHubApiError(GitHubIntegrationError):
    """Raised for any other GitHub failure: timeout, 5xx, unexpected status."""

    def __init__(self, message="GitHub API request failed", status_code=None):
        self.status_code = status_code
        super().__init__(message)