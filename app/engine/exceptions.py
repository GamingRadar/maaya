"""Custom exceptions for inference operations."""


class InferenceError(Exception):
    """Base exception for inference failures."""


class ModelNotFoundError(InferenceError):
    """Raised when the specified GGUF model file cannot be found."""


class ExecutableNotFoundError(InferenceError):
    """Raised when the llama-cli executable cannot be found on PATH or path is invalid."""


class InferenceTimeoutError(InferenceError):
    """Raised when the inference process exceeds the configured timeout."""


class ProcessExecutionError(InferenceError):
    """Raised when the inference subprocess exits with a non-zero exit code."""


class EmptyResponseError(InferenceError):
    """Raised when inference finishes but returns no usable output."""
