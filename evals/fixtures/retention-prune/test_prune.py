import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog import SnapshotCatalog
from policy import RetentionPolicy
from pruner import Pruner, SimulatedInterrupt

HOUR = 3600.0


class ManualClock:
    def __init__(self, value=100 * HOUR):
        self.value = value

    def __call__(self):
        return self.value


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.clock = ManualClock()
        self.catalog = SnapshotCatalog(Path(self.temp.name) / "catalog.sqlite", clock=self.clock)

    def tearDown(self):
        self.catalog.close()
        self.temp.cleanup()

    def add_complete(self, snapshot_id, hours_ago, **kwargs):
        return self.catalog.add(snapshot_id, self.clock.value - hours_ago * HOUR, "complete", **kwargs)

    def add_partial(self, snapshot_id, hours_ago, **kwargs):
        return self.catalog.add(snapshot_id, self.clock.value - hours_ago * HOUR, "partial", **kwargs)

    def test_keep_last_keeps_newest_complete_snapshots(self):
        for index in range(4):
            self.add_complete(f"s{index}", hours_ago=index * 24)
        plan = Pruner(self.catalog, RetentionPolicy(keep_last=2)).plan()
        self.assertEqual(plan.keep, ["s0", "s1"])
        self.assertEqual(plan.delete, ["s2", "s3"])
        self.assertEqual(plan.reasons["s3"], "beyond keep_last")

    def test_pinned_complete_snapshot_beyond_keep_last_is_kept(self):
        self.add_complete("new", hours_ago=1)
        self.add_complete("old-pinned", hours_ago=72, pinned=True)
        self.add_complete("old", hours_ago=96)
        plan = Pruner(self.catalog, RetentionPolicy(keep_last=1)).plan()
        self.assertIn("old-pinned", plan.keep)
        self.assertEqual(plan.reasons["old-pinned"], "pinned")
        self.assertEqual(plan.delete, ["old"])

    def test_protected_tag_beyond_keep_last_is_kept(self):
        self.add_complete("new", hours_ago=1)
        self.add_complete("hold", hours_ago=72, tags=["legal-hold"])
        plan = Pruner(self.catalog, RetentionPolicy(keep_last=1)).plan()
        self.assertEqual(plan.reasons["hold"], "protected tag")
        self.assertEqual(plan.delete, [])

    def test_stale_partial_is_deleted_after_grace(self):
        self.add_complete("new", hours_ago=1)
        self.add_partial("half", hours_ago=7)
        plan = Pruner(self.catalog, RetentionPolicy(keep_last=3, partial_grace_hours=6)).plan()
        self.assertEqual(plan.delete, ["half"])
        self.assertEqual(plan.reasons["half"], "stale partial")

    def test_fresh_partial_is_kept(self):
        self.add_complete("new", hours_ago=1)
        self.add_partial("half", hours_ago=2)
        plan = Pruner(self.catalog, RetentionPolicy(keep_last=3, partial_grace_hours=6)).plan()
        self.assertEqual(plan.delete, [])
        self.assertIn("half", plan.keep)

    def test_apply_marks_deleted_and_removes_payload_once(self):
        self.add_complete("new", hours_ago=1)
        self.add_complete("old", hours_ago=48)
        pruner = Pruner(self.catalog, RetentionPolicy(keep_last=1))
        applied = pruner.apply(pruner.plan())
        self.assertEqual(applied, ["old"])
        self.assertEqual(self.catalog.get("old").state, "deleted")
        self.assertEqual(self.catalog.payload_removals("old"), 1)
        self.assertEqual([t[1] for t in self.catalog.transitions("old")], ["deleting", "deleted"])
        self.assertEqual(self.catalog.get("new").state, "complete")

    def test_interrupt_after_mark_leaves_deleting_state(self):
        self.add_complete("new", hours_ago=1)
        self.add_complete("old", hours_ago=48)
        pruner = Pruner(self.catalog, RetentionPolicy(keep_last=1))
        with self.assertRaises(SimulatedInterrupt):
            pruner.apply(pruner.plan(), interrupt_after_mark=True)
        self.assertEqual(self.catalog.get("old").state, "deleting")
        self.assertEqual(self.catalog.payload_removals("old"), 0)


if __name__ == "__main__":
    unittest.main()
