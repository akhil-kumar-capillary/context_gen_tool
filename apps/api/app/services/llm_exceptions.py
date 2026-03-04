"""Custom exceptions for LLM service calls.

These provide structured error types so callers (orchestrator, tools) can
distinguish transient failures (worth retrying) from permanent ones.
"""


class LLMError(Exception):
    """Base class for all LLM-related errors."""

    def __init__(self, message: str = "LLM Error"):
        super().__init__(message)
        self.message = message


class LLMOverloadedError(LLMError):
    """The LLM provider is overloaded (Anthropic 529 / overloaded_error)."""

    def __init__(self, message: str = "LLM service is overloaded, please try again shortly"):
        super().__init__(message)


class LLMTransientError(LLMError):
    """Transient error that may succeed on retry (429, 5xx, network errors)."""

    def __init__(self, message: str = "LLM service temporarily unavailable"):
        super().__init__(message)
