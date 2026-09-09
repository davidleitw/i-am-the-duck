from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import time


LEASE_SECONDS = 30.0
INITIAL_REVISION = 6


@dataclass(frozen=True)
class Job:
    job_id: str
    report_id: str
    revision: int
    lease_token: int
    lease_until: float | None
    status: str
    receipt: str | None


@dataclass(frozen=True)
class ReportState:
    report_id: str
    requested_revision: int
    active_revision: int


@dataclass(frozen=True)
class FinalizeResult:
    status: str
    active_revision: int


class Catalog:
    """Durable job state and the pointer used by report readers."""

    def __init__(self, path, clock=time.time):
        self.clock = clock
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS reports (
                report_id TEXT PRIMARY KEY,
                requested_revision INTEGER NOT NULL,
                active_revision INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                lease_token INTEGER NOT NULL DEFAULT 0,
                lease_until REAL,
                status TEXT NOT NULL,
                receipt TEXT,
                created_at REAL NOT NULL,
                UNIQUE(report_id, revision),
                FOREIGN KEY(report_id) REFERENCES reports(report_id)
            );
            CREATE INDEX IF NOT EXISTS jobs_claimable
                ON jobs(report_id, status, lease_until, revision);
            """
        )
        self.db.commit()

    def now(self):
        return float(self.clock())

    def request(self, revision, report_id="report", now=None):
        revision = self._revision(revision)
        now = self.now() if now is None else float(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self._ensure_report(report_id)
            row = self.db.execute(
                "SELECT * FROM jobs WHERE report_id = ? AND revision = ?",
                (report_id, revision),
            ).fetchone()
            if row is not None:
                self.db.commit()
                return self._job(row)
            state = self.db.execute(
                "SELECT requested_revision FROM reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()
            if revision <= state["requested_revision"]:
                raise ValueError("new revisions must increase; duplicate requests reuse their job")
            job_id = f"{report_id}:{revision}"
            self.db.execute(
                """INSERT INTO jobs
                   (job_id, report_id, revision, status, created_at)
                   VALUES (?, ?, ?, 'queued', ?)""",
                (job_id, report_id, revision, now),
            )
            self.db.execute(
                "UPDATE reports SET requested_revision = ? WHERE report_id = ?",
                (revision, report_id),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_job(job_id)

    def claim(self, now=None, report_id="report"):
        now = self.now() if now is None else float(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                """SELECT * FROM jobs
                   WHERE report_id = ?
                     AND (status = 'queued'
                          OR (status = 'running' AND lease_until <= ?))
                   ORDER BY revision, job_id LIMIT 1""",
                (report_id, now),
            ).fetchone()
            if row is None:
                self.db.rollback()
                return None
            token = row["lease_token"] + 1
            updated = self.db.execute(
                """UPDATE jobs SET status = 'running', lease_token = ?,
                          lease_until = ?
                   WHERE job_id = ? AND (status = 'queued'
                          OR (status = 'running' AND lease_until <= ?))""",
                (token, now + LEASE_SECONDS, row["job_id"], now),
            ).rowcount
            if updated != 1:
                raise RuntimeError("claim lost")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_job(row["job_id"])

    def save_receipt(self, claim, receipt, now=None):
        now = self.now() if now is None else float(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            changed = self.db.execute(
                """UPDATE jobs SET receipt = ?
                   WHERE job_id = ? AND status = 'running'
                     AND lease_token = ? AND lease_until > ? AND receipt IS NULL""",
                (receipt, claim.job_id, claim.lease_token, now),
            ).rowcount
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return changed == 1

    def finalize(self, claim, now=None):
        now = self.now() if now is None else float(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (claim.job_id,)
            ).fetchone()
            if row is None or row["status"] != "running" or \
                    row["lease_token"] != claim.lease_token or \
                    row["lease_until"] <= now or row["receipt"] is None:
                self.db.rollback()
                return FinalizeResult("stale", self._active(claim.report_id))
            state = self.db.execute(
                "SELECT * FROM reports WHERE report_id = ?", (claim.report_id,)
            ).fetchone()
            if row["revision"] == state["requested_revision"]:
                self.db.execute(
                    "UPDATE reports SET active_revision = ? WHERE report_id = ?",
                    (row["revision"], claim.report_id),
                )
                status = "done"
            else:
                status = "superseded"
            self.db.execute(
                "UPDATE jobs SET status = ?, lease_until = NULL WHERE job_id = ?",
                (status, claim.job_id),
            )
            active = row["revision"] if status == "done" else state["active_revision"]
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return FinalizeResult(status, active)

    def get_job(self, job_id, revision=None):
        if revision is None:
            row = self.db.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT * FROM jobs WHERE report_id = ? AND revision = ?",
                (job_id, revision),
            ).fetchone()
        return self._job(row) if row else None

    def state(self, report_id="report"):
        row = self.db.execute(
            "SELECT * FROM reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        if row is None:
            return ReportState(report_id, INITIAL_REVISION, INITIAL_REVISION)
        return ReportState(report_id, row["requested_revision"], row["active_revision"])

    def close(self):
        self.db.close()

    def _ensure_report(self, report_id):
        self.db.execute(
            "INSERT OR IGNORE INTO reports VALUES (?, ?, ?)",
            (report_id, INITIAL_REVISION, INITIAL_REVISION),
        )

    def _active(self, report_id):
        return self.state(report_id).active_revision

    @staticmethod
    def _revision(value):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("revision must be a positive integer")
        return value

    @staticmethod
    def _job(row):
        return Job(row["job_id"], row["report_id"], row["revision"],
                   row["lease_token"], row["lease_until"], row["status"], row["receipt"])
