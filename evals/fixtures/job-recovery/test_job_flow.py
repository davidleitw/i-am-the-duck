import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from config import JobConfig
from store import JobStore
from worker import JobWorker, PermanentJobError, RetryableJobError, SimulatedCrash


class ManualClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class JobFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.clock = ManualClock()
        self.db_path = Path(self.temp.name) / "jobs.sqlite"
        self.store = JobStore(self.db_path, clock=self.clock)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def submit(self, config=None, job_id="job-1", payload=None):
        return self.store.submit(payload or {"task": "send-report"},
                                 config or JobConfig(max_attempts=3, retry_delay=5), job_id=job_id)

    @staticmethod
    def local_operation(job):
        return {"stand_in": "local-effect", "job_id": job.job_id, "attempt": job.attempt}

    def test_success_claims_once_marks_done_and_records_effect(self):
        job_id = self.submit()
        result = JobWorker(self.store, self.local_operation).run_once()
        self.assertEqual(result.state, "done")
        self.assertEqual((self.store.get(job_id).state, self.store.get(job_id).attempt), ("done", 1))
        self.assertEqual(self.store.effects_for(job_id)[0]["attempt"], 1)

    def test_retryable_failure_waits_for_delay_then_fails_at_limit(self):
        job_id = self.submit(JobConfig(max_attempts=2, retry_delay=10))

        def always_temporary(_job):
            raise RetryableJobError("database is busy")

        worker = JobWorker(self.store, always_temporary)
        self.assertEqual(worker.run_once().state, "queued")
        self.assertEqual(self.store.get(job_id).available_at, 1010.0)
        self.clock.advance(9)
        self.assertIsNone(worker.run_once())
        self.clock.advance(1)
        self.assertEqual(worker.run_once().state, "failed")
        self.assertEqual(self.store.effects_for(job_id), [])

    def test_retryable_failure_can_recover_before_limit(self):
        job_id = self.submit(JobConfig(max_attempts=3, retry_delay=4))

        def temporary_once(job):
            if job.attempt == 1:
                raise RetryableJobError("temporary upstream failure")
            return {"stand_in": "local-effect"}

        worker = JobWorker(self.store, temporary_once)
        self.assertEqual(worker.run_once().state, "queued")
        self.clock.advance(4)
        self.assertEqual(worker.run_once().state, "done")
        self.assertEqual(self.store.get(job_id).attempt, 2)

    def test_permanent_failure_is_failed_without_retry(self):
        job_id = self.submit()
        worker = JobWorker(self.store, lambda _job: (_ for _ in ()).throw(PermanentJobError("bad payload")))
        self.assertEqual(worker.run_once().state, "failed")
        self.assertIsNone(worker.run_once())
        self.assertEqual(self.store.get(job_id).last_error, "bad payload")

    def test_crash_after_effect_can_duplicate_after_resubmit(self):
        job_id = self.submit()
        worker = JobWorker(self.store, self.local_operation)
        with self.assertRaises(SimulatedCrash):
            worker.run_once(crash_after_effect=True)
        self.assertEqual(self.store.get(job_id).state, "running")
        self.store.resubmit(job_id)
        self.assertEqual(worker.run_once().state, "done")
        self.assertEqual(len(self.store.effects_for(job_id)), 2)

    def test_restart_does_not_reclaim_running_job(self):
        job_id = self.submit()
        self.assertEqual(self.store.claim_ready().state, "running")
        self.store.close()
        self.store = JobStore(self.db_path, clock=self.clock)
        self.assertIsNone(self.store.claim_ready())
        self.store.resubmit(job_id)
        self.assertEqual(JobWorker(self.store, self.local_operation).run_once().state, "done")

    def test_resubmit_failed_reuses_payload_and_resets_attempt(self):
        payload = {"task": "send-report", "recipient": "local"}
        job_id = self.submit(payload=payload)
        JobWorker(self.store, lambda _job: (_ for _ in ()).throw(PermanentJobError("bad destination"))).run_once()
        self.store.resubmit(job_id)
        queued = self.store.get(job_id)
        self.assertEqual((queued.state, queued.attempt, queued.payload), ("queued", 0, payload))

    def test_resubmit_running_requeues_same_job(self):
        payload = {"task": "rebuild-index", "partition": 2}
        job_id = self.submit(payload=payload)
        self.assertEqual(self.store.claim_ready().attempt, 1)
        self.store.resubmit(job_id)
        queued = self.store.get(job_id)
        self.assertEqual((queued.state, queued.attempt, queued.payload), ("queued", 0, payload))


if __name__ == "__main__":
    unittest.main()
