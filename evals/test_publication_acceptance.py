import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


FIXTURE = Path(__file__).parent / "fixtures" / "publication-recovery"
sys.path.insert(0, str(FIXTURE))

from publisher import Publisher, SimulatedCrash  # noqa: E402


class AcceptanceClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


class PublicationAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.paths = (root / "catalog.sqlite", root / "storage.sqlite")
        self.clock = AcceptanceClock()
        self.publishers = []

    def tearDown(self):
        for publisher in self.publishers:
            publisher.close()
        self.temp.cleanup()

    def publisher(self):
        value = Publisher(*self.paths, clock=self.clock)
        self.publishers.append(value)
        return value

    @staticmethod
    def seed_initial(publisher):
        publisher.storage.put("report", 6)

    def test_crash_after_put_is_repeated_but_object_is_not_duplicated(self):
        a, b = self.publisher(), self.publisher()
        self.seed_initial(a)
        a.request(7, now=0)
        claim_a = a.claim(now=0)
        with self.assertRaises(SimulatedCrash):
            a.deliver(claim_a, now=0, crash_after_put=True)
        self.assertEqual(a.read_current().revision, 6)

        claim_b = b.claim(now=31)
        result = b.deliver(claim_b, now=31)
        self.assertEqual(result.status, "done")
        self.assertEqual(b.read_current().revision, 7)
        calls = [call for call in b.storage.calls() if call.revision == 7]
        self.assertEqual(len(calls), 2)
        self.assertEqual(len({call.object_id for call in calls}), 1)

    def test_reclaimed_token_stops_old_worker_after_its_put(self):
        a, b = self.publisher(), self.publisher()
        self.seed_initial(a)
        a.request(7, now=0)
        claim_a = a.claim(now=0)
        claim_b = b.claim(now=30)

        stale = a.deliver(claim_a, now=30)
        self.assertEqual(stale.status, "stale")
        self.assertIsNone(a.catalog.get_job(claim_a.job_id).receipt)
        self.assertEqual(a.read_current().revision, 6)

        result = b.deliver(claim_b, now=30)
        self.assertEqual(result.status, "done")
        self.assertEqual(b.read_current().revision, 7)
        calls = [call for call in b.storage.calls() if call.revision == 7]
        self.assertEqual(len(calls), 2)
        self.assertEqual(len({call.object_id for call in calls}), 1)

    def test_obsolete_receipt_is_retained_but_cannot_activate(self):
        publisher = self.publisher()
        self.seed_initial(publisher)
        publisher.request(7, now=0)
        claim = publisher.claim(now=0)
        with self.assertRaises(SimulatedCrash):
            publisher.deliver(claim, now=0, crash_after_receipt=True)
        publisher.request(8, now=1)

        result = publisher.catalog.finalize(claim, now=1)
        self.assertEqual(result.status, "superseded")
        failed_before_upload = publisher.claim(now=2)
        self.assertEqual((failed_before_upload.revision, failed_before_upload.status),
                         (8, "running"))
        self.assertEqual(publisher.read_current().revision, 6)
        self.assertEqual(publisher.catalog.state().requested_revision, 8)
        self.assertEqual(publisher.catalog.get_job(claim.job_id).receipt, "report@7")
        self.assertEqual(publisher.catalog.get_job(claim.job_id).status, "superseded")
        self.assertEqual(publisher.catalog.get_job("report:8").status, "running")
        self.assertIsNone(publisher.storage.get("report", 8))
        self.assertEqual(publisher.storage.object_count(), 2)

    def test_restart_opens_only_and_scan_resumes_saved_receipt(self):
        first = self.publisher()
        self.seed_initial(first)
        first.request(7, now=0)
        claim = first.claim(now=0)
        with self.assertRaises(SimulatedCrash):
            first.deliver(claim, now=0, crash_after_receipt=True)
        first.close()
        self.publishers.remove(first)

        restarted = self.publisher()
        self.assertEqual(restarted.read_current().revision, 6)
        result = restarted.scan_once(now=31)
        self.assertEqual(result.status, "done")
        self.assertEqual(restarted.read_current().revision, 7)
        calls = [call for call in restarted.storage.calls() if call.revision == 7]
        self.assertEqual(len(calls), 1)
        self.assertEqual(restarted.storage.object_count(), 2)


if __name__ == "__main__":
    unittest.main()
