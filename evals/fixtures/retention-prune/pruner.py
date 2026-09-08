from dataclasses import dataclass, field
from typing import Dict, List, Optional

from catalog import SnapshotCatalog
from policy import RetentionPolicy


class SimulatedInterrupt(RuntimeError):
    """A local stand-in for the process stopping in the middle of apply()."""


@dataclass
class PrunePlan:
    delete: List[str] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)
    reasons: Dict[str, str] = field(default_factory=dict)


class Pruner:
    def __init__(self, catalog: SnapshotCatalog, policy: RetentionPolicy):
        self.catalog = catalog
        self.policy = policy

    def plan(self, now: Optional[float] = None) -> PrunePlan:
        now = self.catalog.now() if now is None else float(now)
        plan = PrunePlan()
        rows = self.catalog.list_active()
        grace = self.policy.partial_grace_hours * 3600.0

        stale = []
        for snap in rows:
            if snap.state == "partial" and now - snap.created_at > grace:
                plan.delete.append(snap.snapshot_id)
                plan.reasons[snap.snapshot_id] = "stale partial"
                stale.append(snap.snapshot_id)

        remaining = [s for s in rows if s.snapshot_id not in stale]
        for index, snap in enumerate(remaining):
            if index < self.policy.keep_last:
                plan.keep.append(snap.snapshot_id)
                plan.reasons[snap.snapshot_id] = "within keep_last"
                continue
            if snap.pinned:
                plan.keep.append(snap.snapshot_id)
                plan.reasons[snap.snapshot_id] = "pinned"
                continue
            if any(tag in self.policy.protected_tags for tag in snap.tags):
                plan.keep.append(snap.snapshot_id)
                plan.reasons[snap.snapshot_id] = "protected tag"
                continue
            plan.delete.append(snap.snapshot_id)
            plan.reasons[snap.snapshot_id] = "beyond keep_last"
        return plan

    def apply(self, plan: PrunePlan, now: Optional[float] = None, interrupt_after_mark: bool = False):
        now = self.catalog.now() if now is None else float(now)
        applied = []
        for snapshot_id in plan.delete:
            self.catalog.transition(snapshot_id, "deleting", now)
            if interrupt_after_mark:
                raise SimulatedInterrupt(f"stopped after marking {snapshot_id}, before payload removal")
            self.catalog.remove_payload(snapshot_id, now)
            self.catalog.transition(snapshot_id, "deleted", now)
            applied.append(snapshot_id)
        return applied
