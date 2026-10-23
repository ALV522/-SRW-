from __future__ import annotations


class V1Error(RuntimeError):
    """Base error for v1 domain/runtime failures."""


class V1InvariantError(V1Error):
    """Raised when a v1 domain invariant would be violated."""


class V1NotFoundError(V1Error):
    """Raised when a requested v1 entity does not exist."""


class V1RevisionConflict(V1Error):
    """Raised when an If-Match precondition does not match current state.

    ADR-0003 S2: the write is refused transactionally (412) and must not
    produce any audit trail, because nothing was written.
    """


class ImportReconciliationError(V1Error):
    """Raised when legacy current-state lineage cannot be reconciled safely."""
