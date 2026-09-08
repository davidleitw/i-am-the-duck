from dataclasses import dataclass


@dataclass(frozen=True)
class JobConfig:
    """Per-job retry settings captured when the job is submitted."""

    max_attempts: int = 3
    retry_delay: float = 10.0

    def __post_init__(self):
        if isinstance(self.max_attempts, bool) or self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.retry_delay < 0:
            raise ValueError("retry_delay must not be negative")
