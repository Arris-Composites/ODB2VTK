"""Errors callers can handle without interpreting console output."""


class ExportError(Exception):
    """Base error for conversion and publication failures."""


class SelectionError(ExportError, ValueError):
    """An export selection is malformed or does not exist in the source."""


class OutputError(ExportError):
    """Output options or destination paths cannot be used."""


class SourceError(ExportError):
    """The source cannot provide consistent export data."""


class ExportFailure(ExportError):
    """An operation failed; result describes only files already published."""

    def __init__(self, message, result, cause):
        super(ExportFailure, self).__init__(message)
        self.result = result
        self.cause = cause
