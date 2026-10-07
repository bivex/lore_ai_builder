class LoreDomainError(Exception):
    """Base domain exception."""
    pass


class LoreCanonConflictError(LoreDomainError):
    """Raised when proposed lore contradicts immutable world rules or known canon facts."""
    def __init__(self, entity_name: str, conflicts: list[str]):
        super().__init__(f"Canon conflict in '{entity_name}': {'; '.join(conflicts)}")
        self.entity_name = entity_name
        self.conflicts = conflicts


class InvalidEntityStateError(LoreDomainError):
    """Raised when an operation is invalid for current entity state."""
    pass


class ResourceLimitExceededError(LoreDomainError):
    """Raised when an OS resource constraint is breached."""
    pass
