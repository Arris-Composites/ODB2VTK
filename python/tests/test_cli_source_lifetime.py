"""CLI statuses, resource lifetime, and package execution."""

import contextlib
import io
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core.cli import main
from support import make_source


class CliSourceLifetimeTests(unittest.TestCase):
    def run_cli(self, directory, source, options):
        path = os.path.join(directory, "job.odb")
        Path(path).touch()
        self.factory = Mock(return_value=source)
        with contextlib.redirect_stdout(
            io.StringIO()
        ) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            code = main(
                ["--odbFile", path, "--suffix", "_cli"] + options,
                source_factory=self.factory,
            )
        self.stdout, self.stderr = stdout.getvalue(), stderr.getvalue()
        return code

    def test_successful_conversion_closes_source(self):
        source = make_source()
        with tempfile.TemporaryDirectory() as directory:
            code = self.run_cli(
                directory,
                source,
                [
                    "--header",
                    "0",
                    "--instance",
                    "A",
                    "--step",
                    "Step-1:0",
                    "--writeHistory",
                    "1",
                ],
            )
            self.assertEqual(code, 0, self.stderr)
            self.assertTrue(Path(directory, "job_cli", "Step-1_0.vtu").is_file())
            self.assertTrue(Path(directory, "job_cli", "job_cli.csv").is_file())
        self.assertTrue(source.closed)
        self.assertEqual(source.close_calls, 1)

    def test_header_and_pvd_only_succeed_and_close_source(self):
        for options, path in (
            (["--header", "1"], "job_cli.json"),
            (
                [
                    "--header",
                    "0",
                    "--instance",
                    "A",
                    "--step",
                    "Step-1:0",
                    "--writePVD",
                    "1",
                ],
                os.path.join("job_cli", "job_cli.pvd"),
            ),
        ):
            with self.subTest(
                options=options
            ), tempfile.TemporaryDirectory() as directory:
                source = make_source()
                if "--writePVD" in options:
                    Path(directory, "job_cli").mkdir()
                    Path(directory, "job_cli", "Step-1_0.vtu").touch()
                code = self.run_cli(directory, source, options)
                self.assertEqual(code, 0, self.stderr)
                self.assertTrue(Path(directory, path).is_file())
                self.assertTrue(source.closed)
                self.assertEqual(source.close_calls, 1)

    def test_missing_selection_does_not_open_source(self):
        source = make_source()
        self.addCleanup(source.close)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(self.run_cli(directory, source, ["--header", "0"]), 2)
        self.factory.assert_not_called()
        self.assertIn("--instance is required", self.stderr)
        self.assertFalse(source.closed)

    def test_unknown_instance_returns_argument_error_and_closes_source(self):
        source = make_source()
        with tempfile.TemporaryDirectory() as directory:
            code = self.run_cli(
                directory,
                source,
                ["--header", "0", "--instance", "UNKNOWN", "--step", "Step-1:0"],
            )
        self.assertEqual(code, 2)
        self.assertIn("Instance not found", self.stderr)
        self.assertNotIn("Traceback", self.stderr)
        self.assertTrue(source.closed)

    def test_runtime_failure_returns_one_and_closes_source(self):
        source = make_source()
        source.field_blocks = Mock(side_effect=RuntimeError("bulk read failed"))
        with tempfile.TemporaryDirectory() as directory:
            code = self.run_cli(
                directory,
                source,
                ["--header", "0", "--instance", "A", "--step", "Step-1:0"],
            )
        self.assertEqual(code, 1)
        self.assertIn("bulk read failed", self.stderr)
        self.assertNotIn("Traceback", self.stderr)
        self.assertTrue(source.closed)

    def test_pvd_mode_refuses_missing_vtus(self):
        source = make_source()
        with tempfile.TemporaryDirectory() as directory:
            code = self.run_cli(
                directory,
                source,
                [
                    "--header",
                    "0",
                    "--instance",
                    "A",
                    "--step",
                    "Step-1:0",
                    "--writePVD",
                    "1",
                ],
            )
            self.assertFalse(Path(directory, "job_cli", "job_cli.pvd").exists())
        self.assertEqual(code, 1)
        self.assertIn("VTU file is missing", self.stderr)
        self.assertTrue(source.closed)

    def test_entrypoint_uses_main_return_code(self):
        with patch("odb2vtk_core.cli.main", return_value=7) as cli_main:
            with self.assertRaises(SystemExit) as result:
                runpy.run_module("odb2vtk_core", run_name="__main__")
        self.assertEqual(result.exception.code, 7)
        cli_main.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
