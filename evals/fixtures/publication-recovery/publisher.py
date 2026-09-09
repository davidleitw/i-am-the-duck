from __future__ import annotations

from dataclasses import dataclass
import time

from catalog import Catalog, Job
from storage import Storage


class SimulatedCrash(RuntimeError):
    """A deterministic stop between two durable operations."""


@dataclass(frozen=True)
class DeliveryResult:
    job_id: str
    revision: int
    status: str
    object_id: str | None
    put_called: bool
    receipt_saved: bool


@dataclass(frozen=True)
class ReadResult:
    report_id: str
    revision: int
    object_id: str | None


class Publisher:
    """The only public request, claim, delivery, recovery, and read path."""

    def __init__(self, catalog_path, storage_path, clock=time.time):
        self.clock = clock
        self.catalog = Catalog(catalog_path, clock=clock)
        self.storage = Storage(storage_path)

    def now(self):
        return float(self.clock())

    def request(self, revision, report_id="report", now=None):
        return self.catalog.request(revision, report_id, now)

    def claim(self, now=None, report_id="report"):
        return self.catalog.claim(now, report_id)

    def deliver(self, claim: Job, now=None, crash_after_put=False, crash_after_receipt=False):
        now = self.now() if now is None else float(now)
        object_id = claim.receipt
        put_called = False
        receipt_saved = False
        if object_id is None:
            object_id = self.storage.put(claim.report_id, claim.revision)
            put_called = True
            if crash_after_put:
                raise SimulatedCrash("stopped after put, before saving receipt")
            receipt_saved = self.catalog.save_receipt(claim, object_id, now)
            if not receipt_saved:
                return DeliveryResult(claim.job_id, claim.revision, "stale", object_id,
                                       put_called, receipt_saved)
            if crash_after_receipt:
                raise SimulatedCrash("stopped after saving receipt, before finalization")
        result = self.catalog.finalize(claim, now)
        return DeliveryResult(claim.job_id, claim.revision, result.status, object_id,
                              put_called, receipt_saved)

    def scan_once(self, now=None, report_id="report"):
        claim = self.claim(now, report_id)
        return self.deliver(claim, now=now) if claim is not None else None

    def read_current(self, report_id="report"):
        state = self.catalog.state(report_id)
        stored = self.storage.get(report_id, state.active_revision)
        return ReadResult(report_id, state.active_revision,
                          stored.object_id if stored else None)

    def close(self):
        self.catalog.close()
        self.storage.close()
