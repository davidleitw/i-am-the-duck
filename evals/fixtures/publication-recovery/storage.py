from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class StoredObject:
    object_id: str
    report_id: str
    revision: int


@dataclass(frozen=True)
class PutCall:
    call_id: int
    report_id: str
    revision: int
    object_id: str


class Storage:
    """Local object-store stand-in: calls and immutable objects are separate."""

    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS objects (
                object_id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                UNIQUE(report_id, revision)
            );
            CREATE TABLE IF NOT EXISTS put_calls (
                call_id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                object_id TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def put(self, report_id, revision):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT object_id FROM objects WHERE report_id = ? AND revision = ?",
                (report_id, revision),
            ).fetchone()
            object_id = row["object_id"] if row else f"{report_id}@{revision}"
            if row is None:
                self.db.execute(
                    "INSERT INTO objects VALUES (?, ?, ?)",
                    (object_id, report_id, revision),
                )
            self.db.execute(
                "INSERT INTO put_calls (report_id, revision, object_id) VALUES (?, ?, ?)",
                (report_id, revision, object_id),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return object_id

    def get(self, report_id, revision):
        row = self.db.execute(
            "SELECT * FROM objects WHERE report_id = ? AND revision = ?",
            (report_id, revision),
        ).fetchone()
        return StoredObject(row["object_id"], row["report_id"], row["revision"]) if row else None

    def calls(self, report_id=None):
        query = "SELECT * FROM put_calls"
        args = ()
        if report_id is not None:
            query += " WHERE report_id = ?"
            args = (report_id,)
        rows = self.db.execute(query + " ORDER BY call_id", args).fetchall()
        return [PutCall(row["call_id"], row["report_id"], row["revision"], row["object_id"])
                for row in rows]

    def object_count(self, report_id=None):
        if report_id is None:
            return self.db.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        return self.db.execute(
            "SELECT COUNT(*) FROM objects WHERE report_id = ?", (report_id,)
        ).fetchone()[0]

    def close(self):
        self.db.close()
