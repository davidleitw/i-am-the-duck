import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from config import JobConfig


@dataclass(frozen=True)
class Job:
    job_id: str
    payload: Dict[str, Any]
    state: str
    attempt: int
    max_attempts: int
    retry_delay: float
    available_at: float
    last_error: Optional[str]


class JobStore:
    """SQLite-backed job state and a separate local effect log."""

    def __init__(self, path, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                state TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL,
                retry_delay REAL NOT NULL,
                available_at REAL NOT NULL,
                last_error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS jobs_ready
                ON jobs(state, available_at, created_at);
            CREATE TABLE IF NOT EXISTS effects (
                effect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                detail TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            """
        )
        self.db.commit()

    def now(self) -> float:
        return float(self.clock())

    def submit(self, payload: Dict[str, Any], config: JobConfig, job_id: Optional[str] = None) -> str:
        job_id = job_id or uuid.uuid4().hex
        now = self.now()
        self.db.execute(
            """
            INSERT INTO jobs
                (job_id, payload, state, attempt, max_attempts, retry_delay,
                 available_at, last_error, created_at, updated_at)
            VALUES (?, ?, 'queued', 0, ?, ?, ?, NULL, ?, ?)
            """,
            (job_id, json.dumps(payload, sort_keys=True), config.max_attempts,
             config.retry_delay, now, now, now),
        )
        self.db.commit()
        return job_id

    def get(self, job_id: str) -> Optional[Job]:
        row = self.db.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def claim_ready(self, now: Optional[float] = None) -> Optional[Job]:
        now = self.now() if now is None else float(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                """
                SELECT * FROM jobs
                WHERE state = 'queued' AND available_at <= ?
                ORDER BY created_at, job_id
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                self.db.rollback()
                return None
            updated = self.db.execute(
                """
                UPDATE jobs
                SET state = 'running', attempt = attempt + 1, updated_at = ?
                WHERE job_id = ? AND state = 'queued'
                """,
                (now, row["job_id"]),
            ).rowcount
            if updated != 1:
                raise RuntimeError("job claim lost")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get(row["job_id"])

    def mark_done(self, job_id: str, now: Optional[float] = None) -> None:
        self._update_running(job_id, "done", None, self.now() if now is None else now)

    def queue_retry(self, job: Job, error: str, now: Optional[float] = None) -> None:
        now = self.now() if now is None else float(now)
        updated = self.db.execute(
            """
            UPDATE jobs
            SET state = 'queued', available_at = ?, last_error = ?, updated_at = ?
            WHERE job_id = ? AND state = 'running'
            """,
            (now + job.retry_delay, error, now, job.job_id),
        ).rowcount
        if updated != 1:
            raise ValueError("job is not running")
        self.db.commit()

    def mark_failed(self, job_id: str, error: str, now: Optional[float] = None) -> None:
        self._update_running(job_id, "failed", error, self.now() if now is None else now)

    def resubmit(self, job_id: str, now: Optional[float] = None) -> None:
        now = self.now() if now is None else float(now)
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.state not in {"running", "failed"}:
            raise ValueError("only running or failed jobs can be resubmitted")
        self.db.execute(
            """
            UPDATE jobs
            SET state = 'queued', attempt = 0, available_at = ?,
                last_error = NULL, updated_at = ?
            WHERE job_id = ?
            """,
            (now, now, job_id),
        )
        self.db.commit()

    def record_effect(self, job: Job, detail: Any, now: Optional[float] = None) -> None:
        self.db.execute(
            """
            INSERT INTO effects (job_id, attempt, detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (job.job_id, job.attempt, json.dumps(detail, sort_keys=True),
             self.now() if now is None else float(now)),
        )
        self.db.commit()

    def effects_for(self, job_id: str):
        rows = self.db.execute(
            "SELECT * FROM effects WHERE job_id = ? ORDER BY effect_id", (job_id,)
        ).fetchall()
        return [
            {"attempt": row["attempt"], "detail": json.loads(row["detail"]),
             "created_at": row["created_at"]}
            for row in rows
        ]

    def close(self) -> None:
        self.db.close()

    def _update_running(self, job_id: str, state: str, error: Optional[str], now: float) -> None:
        updated = self.db.execute(
            """
            UPDATE jobs SET state = ?, last_error = ?, updated_at = ?
            WHERE job_id = ? AND state = 'running'
            """,
            (state, error, float(now), job_id),
        ).rowcount
        if updated != 1:
            raise ValueError("job is not running")
        self.db.commit()

    @staticmethod
    def _job(row) -> Job:
        return Job(
            job_id=row["job_id"],
            payload=json.loads(row["payload"]),
            state=row["state"],
            attempt=row["attempt"],
            max_attempts=row["max_attempts"],
            retry_delay=row["retry_delay"],
            available_at=row["available_at"],
            last_error=row["last_error"],
        )
