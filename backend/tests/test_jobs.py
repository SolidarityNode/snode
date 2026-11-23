from __future__ import annotations

import threading

import pytest

from solidaritynode_backend.jobs import InProcessJobRunner, JobRunner, JobStatus


def _wait(runner: InProcessJobRunner, job_id: str) -> JobStatus:
    for _ in range(200):
        status = runner.info(job_id).status
        if status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return status
        threading.Event().wait(0.01)
    raise AssertionError("job did not finish")


def test_runner_satisfies_interface() -> None:
    runner: JobRunner = InProcessJobRunner()
    runner.shutdown()


def test_job_lifecycle() -> None:
    runner = InProcessJobRunner(max_workers=1)
    gate = threading.Event()
    blocking = runner.submit("block", gate.wait)
    queued = runner.submit("ok", lambda: 42)
    assert runner.info(queued).status is JobStatus.PENDING
    gate.set()
    assert _wait(runner, blocking) is JobStatus.SUCCEEDED
    assert _wait(runner, queued) is JobStatus.SUCCEEDED
    runner.shutdown()


def test_failed_job_reports_error() -> None:
    runner = InProcessJobRunner()

    def boom() -> None:
        raise RuntimeError("boom")

    job = runner.submit("boom", boom)
    assert _wait(runner, job) is JobStatus.FAILED
    assert "boom" in (runner.info(job).error or "")
    with pytest.raises(KeyError):
        runner.info("unknown")
    runner.shutdown()
