from __future__ import annotations


class V1Error(RuntimeError):
    """Base error for v1 domain/runtime failures."""


class V1InvariantError(V1Error):
    """Raised when a v1 domain invariant would be violated."""


class V1NotFoundError(V1Error):
    """Raised when a requested v1 entity does not exist."""


class ImportReconciliationError(V1Error):
    """Raised when legacy current-state lineage cannot be reconciled safely."""


class V1RequestValidationError(ValueError):
    """Raised when an HTTP request body fails schema validation (422 invalid_request).

    Subclasses ValueError because the HTTP adapter maps it that way; moved here from
    api/app.py so route modules can raise it without importing the app factory.
    """
