import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple

ACTIVE_STATES = ("complete", "partial")
ALL_STATES = ("complete", "partial", "deleting", "deleted")


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    created_at: float
    state: str
    pinned: bool
    tags: Tuple[str, ...]
    deleted_at: Optional[float] = None


class SnapshotCatalog:
    """SQLite catalog of backup snapshots plus a local stand-in for payload removal."""

    def __init__(self, path: Path, clock: Optional[Callable[[], float]] = None):
        self.clock = clock or time.time
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS snapshots ("
            " snapshot_id TEXT PRIMARY KEY,"
            " created_at REAL NOT NULL,"
            " state TEXT NOT NULL,"
            " pinned INTEGER NOT NULL DEFAULT 0,"
            " tags TEXT NOT NULL DEFAULT '[]',"
            " deleted_at REAL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS transitions ("
            " seq INTEGER PRIMARY KEY AUTOINCREMENT,"
            " snapshot_id TEXT NOT NULL,"
            " from_state TEXT NOT NULL,"
            " to_state TEXT NOT NULL,"
            " at REAL NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS payload_removals ("
            " seq INTEGER PRIMARY KEY AUTOINCREMENT,"
            " snapshot_id TEXT NOT NULL,"
            " at REAL NOT NULL)"
        )

    def close(self):
        self.conn.close()

    def now(self) -> float:
        return float(self.clock())

    def add(self, snapshot_id: str, created_at: float, state: str = "complete",
            pinned: bool = False, tags: Iterable[str] = ()) -> Snapshot:
        if state not in ACTIVE_STATES:
            raise ValueError(f"new snapshots must be complete or partial, got {state!r}")
        self.conn.execute(
            "INSERT INTO snapshots (snapshot_id, created_at, state, pinned, tags) VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, float(created_at), state, int(bool(pinned)), json.dumps(sorted(tags))),
        )
        return self.get(snapshot_id)

    def get(self, snapshot_id: str) -> Optional[Snapshot]:
        row = self.conn.execute(
            "SELECT snapshot_id, created_at, state, pinned, tags, deleted_at FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        return self._row(row) if row else None

    def list_active(self) -> List[Snapshot]:
        rows = self.conn.execute(
            "SELECT snapshot_id, created_at, state, pinned, tags, deleted_at FROM snapshots"
            " WHERE state IN ('complete', 'partial') ORDER BY created_at DESC, snapshot_id"
        ).fetchall()
        return [self._row(r) for r in rows]

    def list_state(self, state: str) -> List[Snapshot]:
        if state not in ALL_STATES:
            raise ValueError(f"unknown state {state!r}")
        rows = self.conn.execute(
            "SELECT snapshot_id, created_at, state, pinned, tags, deleted_at FROM snapshots"
            " WHERE state = ? ORDER BY created_at DESC, snapshot_id",
            (state,),
        ).fetchall()
        return [self._row(r) for r in rows]

    def set_pinned(self, snapshot_id: str, pinned: bool):
        self.conn.execute("UPDATE snapshots SET pinned = ? WHERE snapshot_id = ?",
                          (int(bool(pinned)), snapshot_id))

    def transition(self, snapshot_id: str, to_state: str, now: Optional[float] = None) -> Snapshot:
        if to_state not in ALL_STATES:
            raise ValueError(f"unknown state {to_state!r}")
        now = self.now() if now is None else float(now)
        current = self.get(snapshot_id)
        if current is None:
            raise KeyError(snapshot_id)
        with self.conn:
            self.conn.execute("BEGIN")
            self.conn.execute(
                "UPDATE snapshots SET state = ?, deleted_at = ? WHERE snapshot_id = ?",
                (to_state, now if to_state == "deleted" else current.deleted_at, snapshot_id),
            )
            self.conn.execute(
                "INSERT INTO transitions (snapshot_id, from_state, to_state, at) VALUES (?, ?, ?, ?)",
                (snapshot_id, current.state, to_state, now),
            )
        return self.get(snapshot_id)

    def remove_payload(self, snapshot_id: str, now: Optional[float] = None):
        """Local stand-in for deleting the snapshot's data. Not idempotent-checked."""
        now = self.now() if now is None else float(now)
        self.conn.execute("INSERT INTO payload_removals (snapshot_id, at) VALUES (?, ?)",
                          (snapshot_id, now))

    def payload_removals(self, snapshot_id: str) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM payload_removals WHERE snapshot_id = ?",
                                (snapshot_id,)).fetchone()
        return int(row[0])

    def transitions(self, snapshot_id: str) -> List[Tuple[str, str, float]]:
        rows = self.conn.execute(
            "SELECT from_state, to_state, at FROM transitions WHERE snapshot_id = ? ORDER BY seq",
            (snapshot_id,),
        ).fetchall()
        return [(r[0], r[1], float(r[2])) for r in rows]

    @staticmethod
    def _row(row) -> Snapshot:
        return Snapshot(
            snapshot_id=row[0], created_at=float(row[1]), state=row[2], pinned=bool(row[3]),
            tags=tuple(json.loads(row[4])), deleted_at=row[5],
        )
