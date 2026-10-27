"""Shared argument validation and worker receipt outcomes."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core.cli import main, parse_request, request_payload, worker_main
from support import make_source


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="odb2vtk cli ")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name, "job with & % characters.odb")
        self.path.touch()
        self.arguments = [
            "--header",
            "0",
            "--odbFile",
            str(self.path),
            "--instance",
            "A",
            "B",
            "--step",
            "Step-1:0",
            "--suffix",
            "_space suffix",
        ]

    def test_both_entrypoints_share_selection_and_output_parsing(self):
        single = parse_request(self.arguments)
        parallel = parse_request(self.arguments + ["--jobs", "2"], parallel=True)
        self.assertEqual(single.selection, parallel.selection)
        self.assertEqual(single.outputs, parallel.outputs)
        self.assertEqual(parallel.jobs, 2)
        self.assertEqual(single.outputs.suffix, "_space suffix")

    def test_invalid_frame_lists_and_duplicates_are_argument_errors(self):
        for tokens in (
            ["Step-1"],
            [":0"],
            ["Step-1:"],
            ["Step-1:-1"],
            ["Step-1:0,,1"],
            ["Step-1:0-3"],
            ["Step-1:0.0"],
            ["Step-1:0,0"],
            ["Step-1:0", "Step-1:1"],
        ):
            with self.subTest(tokens=tokens), contextlib.redirect_stderr(
                io.StringIO()
            ) as stderr:
                factory = Mock()
                code = main(
                    [
                        "--header",
                        "0",
                        "--odbFile",
                        str(self.path),
                        "--instance",
                        "A",
                        "--step",
                    ]
                    + tokens,
                    source_factory=factory,
                )
                self.assertEqual(code, 2)
                factory.assert_not_called()
                self.assertNotIn("Traceback", stderr.getvalue())

    def test_invalid_flags_and_jobs_are_rejected(self):
        for extra in (
            ["--header", "2"],
            ["--writePVD", "2"],
            ["--writeHistory", "2"],
            ["--jobs", "0"],
            ["--jobs", "bad"],
        ):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    parse_request(self.arguments + extra, parallel=True)
                self.assertEqual(result.exception.code, 2)

    def test_header_mode_ignores_step_selection(self):
        request = parse_request(
            ["--header", "1", "--odbFile", str(self.path), "--step", "not-a-frame-list"]
        )
        self.assertEqual(request.mode, "header")
        self.assertIsNone(request.selection)

    def test_help_and_missing_file_do_not_open_a_source(self):
        factory = Mock()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            self.assertEqual(main(["--help"], source_factory=factory), 0)
            self.assertEqual(
                main(
                    ["--header", "1", "--odbFile", str(self.path) + ".missing"],
                    source_factory=factory,
                ),
                2,
            )
        factory.assert_not_called()

    def test_output_conflicts_fail_preflight_without_mesh_conversion(self):
        request = parse_request(self.arguments)
        Path(request.outputs.data_directory).mkdir()
        Path(request.outputs.collection_path).mkdir()
        source = make_source()
        source.mesh = Mock(side_effect=AssertionError("mesh conversion started"))
        job, receipt = self.write_job(
            request._replace(outputs=request.outputs._replace(write_pvd=True)),
            validate=True,
        )
        with contextlib.redirect_stderr(io.StringIO()):
            code = worker_main(job, receipt, source_factory=lambda path: source)
        self.assertEqual(code, 1)
        source.mesh.assert_not_called()
        self.assertTrue(source.closed)

    def write_job(self, request, validate=False):
        job = Path(self.directory.name, "request.json")
        receipt = Path(self.directory.name, "result.json")
        job.write_text(json.dumps(request_payload(request, validate)), encoding="utf-8")
        return str(job), str(receipt)

    def test_success_receipt_is_written_after_source_closure(self):
        request = parse_request(self.arguments)
        job, receipt = self.write_job(request)
        source = make_source()
        self.assertEqual(
            worker_main(job, receipt, source_factory=lambda path: source), 0
        )
        self.assertTrue(source.closed)
        result = json.loads(Path(receipt).read_text())
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["paths"], [request.outputs.frame_path("Step-1", 0)])
        self.assertTrue(Path(result["paths"][0]).is_file())

    def test_receipt_records_failure_even_without_process_exit_propagation(self):
        arguments = list(self.arguments)
        arguments[arguments.index("--step") + 1] = "UNKNOWN:0"
        job, receipt = self.write_job(parse_request(arguments))
        source = make_source()
        with contextlib.redirect_stderr(io.StringIO()):
            code = worker_main(job, receipt, source_factory=lambda path: source)
        result = json.loads(Path(receipt).read_text())
        self.assertEqual(code, 2)
        self.assertEqual(result["code"], 2)
        self.assertEqual(result["paths"], [])
        self.assertTrue(source.closed)

    def test_failed_source_close_preserves_completed_paths_in_receipt(self):
        request = parse_request(self.arguments)
        job, receipt = self.write_job(request)
        source = make_source()
        close = source.close

        def failed_close():
            close()
            raise OSError("source close failed")

        source.close = failed_close
        with contextlib.redirect_stderr(io.StringIO()):
            code = worker_main(job, receipt, source_factory=lambda path: source)
        result = json.loads(Path(receipt).read_text())
        self.assertEqual(code, 1)
        self.assertIn("source close failed", result["error"])
        self.assertEqual(result["paths"], [request.outputs.frame_path("Step-1", 0)])
        self.assertTrue(source.closed)

    def test_thin_scripts_support_help_from_another_working_directory(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("odb2vtk.py", "multiprocess.py"):
            with self.subTest(script=name):
                result = subprocess.run(
                    [sys.executable, str(root / name), "--help"],
                    cwd=self.directory.name,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--odbFile", result.stdout)

    def test_help_does_not_require_site_packages_or_numpy(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("odb2vtk.py", "multiprocess.py"):
            with self.subTest(script=name):
                result = subprocess.run(
                    [sys.executable, "-S", str(root / name), "--help"],
                    cwd=self.directory.name,
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--odbFile", result.stdout)


if __name__ == "__main__":
    unittest.main()
