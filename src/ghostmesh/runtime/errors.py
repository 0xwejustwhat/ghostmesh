from __future__ import annotations


class RuntimeErrorBase(ValueError):
    """Base class for runtime operation errors."""


class NotFoundError(RuntimeErrorBase):
    """Raised when a runtime resource cannot be found."""


class ConflictError(RuntimeErrorBase):
    """Raised when a runtime operation conflicts with current state."""


class InvalidOperationError(RuntimeErrorBase):
    """Raised when an operation is not allowed by the registered Patch Panel."""

