from __future__ import annotations


class PatchPanelLoadError(ValueError):
    """Raised when a Patch Panel file cannot be loaded or parsed."""


class PatchPanelValidationError(ValueError):
    """Raised when a Patch Panel fails semantic graph validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))

