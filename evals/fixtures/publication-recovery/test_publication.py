import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from publisher import Publisher, SimulatedCrash


class Clock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.clock = Clock()
        root = Path(self.temp.name)
        self.paths = (root / "catalog.sqlite", root / "storage.sqlite")
        self.publisher = Publisher(*self.paths, clock=self.clock)

    def tearDown(self):
        self.publisher.close()
        self.temp.cleanup()

    def test_ordinary_publication_moves_reader_pointer(self):
        self.publisher.storage.put("report", 6)
        job = self.publisher.request(7)
        claim = self.publisher.claim()
        result = self.publisher.deliver(claim)
        self.assertEqual((result.status, job.job_id), ("done", claim.job_id))
        self.assertEqual(self.publisher.read_current().revision, 7)
        self.assertEqual(self.publisher.catalog.state().requested_revision, 7)

    def test_storage_deduplicates_objects_but_records_each_put(self):
        first = self.publisher.storage.put("report", 7)
        second = self.publisher.storage.put("report", 7)
        self.assertEqual(first, second)
        self.assertEqual(len(self.publisher.storage.calls()), 2)
        self.assertEqual(self.publisher.storage.object_count(), 1)

    def test_claim_at_lease_boundary_replaces_old_token(self):
        self.publisher.request(7)
        first = self.publisher.claim(now=0)
        self.assertIsNone(self.publisher.claim(now=29))
        second = self.publisher.claim(now=30)
        self.assertEqual((first.lease_token, second.lease_token), (1, 2))
        self.assertEqual(second.lease_until, 60.0)

    def test_scan_once_is_explicit_receipt_recovery(self):
        self.publisher.storage.put("report", 6)
        self.publisher.request(7)
        claim = self.publisher.claim(now=0)
        with self.assertRaises(SimulatedCrash):
            self.publisher.deliver(claim, now=0, crash_after_receipt=True)
        self.assertEqual(self.publisher.read_current().revision, 6)
        self.publisher.close()
        self.publisher = Publisher(*self.paths, clock=self.clock)
        self.assertEqual(self.publisher.read_current().revision, 6)
        result = self.publisher.scan_once(now=31)
        self.assertEqual(result.status, "done")
        self.assertEqual(self.publisher.read_current().revision, 7)
        self.assertEqual(len([call for call in self.publisher.storage.calls()
                              if call.revision == 7]), 1)


if __name__ == "__main__":
    unittest.main()
