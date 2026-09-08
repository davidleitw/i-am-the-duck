from dataclasses import dataclass


@dataclass(frozen=True)
class RetentionPolicy:
    """Retention settings applied by one prune pass."""

    keep_last: int = 3
    partial_grace_hours: float = 6.0
    protected_tags: frozenset = frozenset({"legal-hold"})

    def __post_init__(self):
        if isinstance(self.keep_last, bool) or self.keep_last < 1:
            raise ValueError("keep_last must be at least 1")
        if self.partial_grace_hours < 0:
            raise ValueError("partial_grace_hours must not be negative")
