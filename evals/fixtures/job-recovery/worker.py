from dataclasses import dataclass
from typing import Any, Callable, Optional

from store import Job, JobStore


class RetryableJobError(Exception):
    pass


class PermanentJobError(Exception):
    pass


class SimulatedCrash(RuntimeError):
    """A local stand-in for a process stop between two durable writes."""


@dataclass(frozen=True)
class RunResult:
    job_id: str
    state: str
    attempt: int
    error: Optional[str] = None


class JobWorker:
    def __init__(self, store: JobStore, operation: Callable[[Job], Any]):
        self.store = store
        self.operation = operation

    def run_once(self, now: Optional[float] = None, crash_after_effect: bool = False):
        now = self.store.now() if now is None else float(now)
        job = self.store.claim_ready(now)
        if job is None:
            return None
        try:
            detail = self.operation(job)
        except RetryableJobError as exc:
            error = str(exc)
            if job.attempt >= job.max_attempts:
                self.store.mark_failed(job.job_id, error, now)
                return RunResult(job.job_id, "failed", job.attempt, error)
            self.store.queue_retry(job, error, now)
            return RunResult(job.job_id, "queued", job.attempt, error)
        except PermanentJobError as exc:
            error = str(exc)
            self.store.mark_failed(job.job_id, error, now)
            return RunResult(job.job_id, "failed", job.attempt, error)
        except Exception as exc:
            error = f"unexpected error: {exc}"
            self.store.mark_failed(job.job_id, error, now)
            return RunResult(job.job_id, "failed", job.attempt, error)

        self.store.record_effect(job, detail, now)
        if crash_after_effect:
            raise SimulatedCrash("stopped after local effect, before job completion")
        self.store.mark_done(job.job_id, now)
        return RunResult(job.job_id, "done", job.attempt)
