"""Parallel scheduling and completion receipts without an Abaqus installation."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core.cli import parse_request, worker_main
from odb2vtk_core.models import ExportResult, FrameExport, Selection
from odb2vtk_core.parallel import (
    AbaqusWorker,
    WorkerError,
    expected_paths,
    main,
    run_parallel,
)
from support import make_source


class FakeWorker:
    def __init__(self, barrier=None, fail=None, missing=False):
        self.requests = []
        self.barrier, self.fail, self.missing = barrier, fail, missing
        self.lock = threading.Lock()
        self.active, self.maximum, self.finished = 0, 0, 0

    def __call__(self, request, validate_only=False):
        self.requests.append((request, validate_only))
        if validate_only:
            if self.fail == "preflight":
                raise WorkerError("invalid source selection", code=2)
            return ExportResult((), (), ())
        if request.mode == "frames":
            with self.lock:
                self.active += 1
                self.maximum = max(self.maximum, self.active)
            try:
                if self.barrier is not None:
                    self.barrier.wait(timeout=5)
                step, frames = request.selection.steps[0]
                frame = frames[0]
                if self.fail == "frame" and frame == 1:
                    raise WorkerError("frame worker failed")
                paths = expected_paths(request)
                if not self.missing or frame != 0:
                    for path in paths:
                        Path(path).parent.mkdir(parents=True, exist_ok=True)
                        Path(path).write_text("completed frame")
                with self.lock:
                    self.finished += 1
                return ExportResult(
                    paths, (FrameExport(step, frame, float(frame), paths[-1]),), ()
                )
            finally:
                with self.lock:
                    self.active -= 1
        if request.mode == "collection":
            expected = sum(len(frames) for _, frames in request.selection.steps)
            if self.finished != expected:
                raise AssertionError("collection started before frame workers finished")
            if self.fail == "collection":
                raise WorkerError("collection worker failed")
        paths = expected_paths(request)
        for path in paths:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("completed aggregate")
        return ExportResult(paths, (), ())


class ParallelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="parallel paths ")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name, "job & % name.odb")
        self.path.touch()
        self.arguments = [
            "--header",
            "0",
            "--odbFile",
            str(self.path),
            "--instance",
            "A",
            "--step",
            "Step-1:0,1",
            "--suffix",
            "_space suffix",
            "--jobs",
            "2",
        ]
        self.request = parse_request(self.arguments, parallel=True)

    def test_preflight_then_bounded_workers_then_history_and_collection_once(self):
        worker = FakeWorker(barrier=threading.Barrier(2))
        request = self.request._replace(write_history=True)
        result = run_parallel(request, worker)
        self.assertTrue(worker.requests[0][1])
        self.assertTrue(worker.requests[0][0].outputs.write_pvd)
        self.assertEqual(worker.requests[-1][0].mode, "collection")
        self.assertEqual(worker.maximum, 2)
        self.assertEqual(worker.active, 0)
        history_modes = [
            r.mode
            for r, validate in worker.requests
            if r.write_history and not validate
        ]
        self.assertEqual(history_modes, ["collection"])
        self.assertEqual([frame.frame for frame in result.frames], [0, 1])
        self.assertEqual(len(result.paths), 4)
        self.assertTrue(all(Path(path).is_file() for path in result.paths))

    def test_preflight_failure_starts_no_frame_jobs_or_output_directory(self):
        worker = FakeWorker(fail="preflight")
        with self.assertRaises(WorkerError) as result:
            run_parallel(self.request, worker)
        self.assertEqual(result.exception.code, 2)
        self.assertEqual(len(worker.requests), 1)
        self.assertFalse(Path(self.request.outputs.data_directory).exists())

    def test_binary_option_is_preserved_for_preflight_frame_and_collection_jobs(self):
        worker = FakeWorker()
        request = parse_request(self.arguments + ["--format", "binary"], parallel=True)
        run_parallel(request, worker)
        self.assertTrue(worker.requests)
        self.assertTrue(
            all(r.outputs.vtu_format == "binary" for r, _ in worker.requests)
        )

    def test_worker_failure_drains_active_jobs_and_never_schedules_collection(self):
        worker = FakeWorker(barrier=threading.Barrier(2), fail="frame")
        with self.assertRaises(WorkerError) as result:
            run_parallel(self.request, worker)
        self.assertEqual(worker.active, 0)
        self.assertEqual(len(result.exception.completed_paths), 1)
        self.assertFalse(any(r.mode == "collection" for r, _ in worker.requests))
        self.assertFalse(Path(self.request.outputs.collection_path).exists())

    def test_missing_completed_file_prevents_collection(self):
        worker = FakeWorker(missing=True)
        with self.assertRaisesRegex(WorkerError, "missing VTU"):
            run_parallel(self.request, worker)
        self.assertFalse(any(r.mode == "collection" for r, _ in worker.requests))

    def test_final_worker_failure_reports_completed_vtus(self):
        worker = FakeWorker(fail="collection")
        with self.assertRaises(WorkerError) as result:
            run_parallel(self.request, worker)
        self.assertEqual(len(result.exception.completed_paths), 2)
        self.assertTrue(
            all(Path(path).is_file() for path in result.exception.completed_paths)
        )

    def test_one_job_runs_sequentially(self):
        worker = FakeWorker()
        run_parallel(self.request._replace(jobs=1), worker)
        self.assertEqual(worker.maximum, 1)

    def test_parallel_cli_propagates_worker_failure_codes(self):
        for fail, expected in (("preflight", 2), ("frame", 1)):
            with self.subTest(fail=fail), contextlib.redirect_stdout(
                io.StringIO()
            ), contextlib.redirect_stderr(io.StringIO()):
                code = main(
                    self.arguments,
                    worker_factory=lambda workspace: FakeWorker(fail=fail),
                )
            self.assertEqual(code, expected)

    def test_parallel_header_mode_does_not_schedule_frames(self):
        worker = FakeWorker()
        request = parse_request(
            ["--header", "1", "--odbFile", str(self.path)], parallel=True
        )
        result = run_parallel(request, worker)
        self.assertEqual(len(worker.requests), 1)
        self.assertEqual(result.paths, (request.outputs.header_path,))


class WorkerReceiptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="worker json ")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name, "job & % name.odb")
        self.path.touch()
        self.request = parse_request(
            [
                "--header",
                "0",
                "--odbFile",
                str(self.path),
                "--instance",
                "A",
                "--step",
                "Step-1:0",
                "--suffix",
                "_with spaces",
            ]
        )
        self.workspace = Path(self.directory.name, "transport directory")
        self.workspace.mkdir()
        self.calls = []

    def launch(self, command, **options):
        self.calls.append((command, options))
        environment = options["env"]
        with contextlib.redirect_stderr(io.StringIO()):
            worker_main(
                environment["ODB2VTK_JOB_FILE"],
                environment["ODB2VTK_RESULT_FILE"],
                source_factory=lambda path: make_source(),
            )
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    def test_request_data_is_not_interpolated_into_the_command(self):
        worker = AbaqusWorker(
            str(self.workspace), command=(sys.executable,), launch=self.launch
        )
        result = worker(self.request)
        command, options = self.calls[0]
        self.assertEqual(command, [sys.executable, "worker.py"])
        self.assertFalse(options["shell"])
        self.assertEqual(options["cwd"], str(self.workspace))
        payload = json.loads(Path(options["env"]["ODB2VTK_JOB_FILE"]).read_text())
        self.assertEqual(payload["odb_file"], str(self.path))
        self.assertEqual(payload["outputs"]["suffix"], "_with spaces")
        self.assertEqual(result.paths, (self.request.outputs.frame_path("Step-1", 0),))

    def test_zero_launcher_status_without_a_receipt_is_failure_even_with_old_output(
        self,
    ):
        target = Path(self.request.outputs.frame_path("Step-1", 0))
        target.parent.mkdir()
        target.write_text("stale file")
        worker = AbaqusWorker(
            str(self.workspace),
            command=(sys.executable,),
            launch=lambda *args, **kwargs: types.SimpleNamespace(
                returncode=0, stdout="", stderr=""
            ),
        )
        with self.assertRaisesRegex(WorkerError, "completion receipt"):
            worker(self.request)

    def test_receipt_detects_failure_masked_by_zero_launcher_status(self):
        worker = AbaqusWorker(
            str(self.workspace), command=(sys.executable,), launch=self.launch
        )
        bad = self.request._replace(selection=Selection(["UNKNOWN"], {"Step-1": [0]}))
        with self.assertRaises(WorkerError) as result:
            worker(bad)
        self.assertEqual(result.exception.code, 2)

    def test_nonzero_launcher_status_is_failure_even_with_a_success_receipt(self):
        def launch(command, **options):
            result = self.launch(command, **options)
            result.returncode = 9
            return result

        worker = AbaqusWorker(
            str(self.workspace), command=(sys.executable,), launch=launch
        )
        with self.assertRaises(WorkerError) as result:
            worker(self.request)
        self.assertEqual(result.exception.completed_paths, expected_paths(self.request))

    def test_success_receipt_must_list_all_expected_outputs(self):
        def launch(command, **options):
            result = self.launch(command, **options)
            receipt = Path(options["env"]["ODB2VTK_RESULT_FILE"])
            data = json.loads(receipt.read_text())
            data["paths"] = []
            receipt.write_text(json.dumps(data))
            return result

        worker = AbaqusWorker(
            str(self.workspace), command=(sys.executable,), launch=launch
        )
        with self.assertRaisesRegex(WorkerError, "all requested"):
            worker(self.request)

    def test_success_receipt_cannot_claim_missing_files(self):
        def launch(command, **options):
            result = self.launch(command, **options)
            Path(self.request.outputs.frame_path("Step-1", 0)).unlink()
            return result

        worker = AbaqusWorker(
            str(self.workspace), command=(sys.executable,), launch=launch
        )
        with self.assertRaisesRegex(WorkerError, "missing"):
            worker(self.request)


if __name__ == "__main__":
    unittest.main()
