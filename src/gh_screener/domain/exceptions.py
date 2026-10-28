class DomainError(Exception):
    """Base class for expected domain errors."""


class InvalidProfileError(DomainError):
    """Raised when a profile identifier cannot be used."""


class ProfileNotFoundError(DomainError):
    """Raised when GitHub has no profile for the requested username."""


class UnknownCriteriaOptionError(DomainError):
    """Raised when a user selects an unsupported criteria option."""
