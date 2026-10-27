"""Exercise existing CLI paths with an injected source factory."""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core.source import AbaqusSource
from odb2vtk_core.errors import SelectionError
from support import make_source


class CliSourceLifetimeTests(unittest.TestCase):
    def run_cli(self, directory, source, options):
        odb_path = os.path.join(directory, "job.odb")
        with open(odb_path, "w"):
            pass
        script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "odb2vtk.py")
        arguments = [script, "--odbFile", odb_path, "--suffix", "_cli"] + options
        with patch.object(AbaqusSource, "open", return_value=source), patch.object(
            sys, "argv", arguments
        ), contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(script, run_name="__main__")

    def test_successful_conversion_closes_source(self):
        source = make_source()
        with tempfile.TemporaryDirectory() as directory:
            self.run_cli(
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
            self.assertTrue(
                os.path.isfile(os.path.join(directory, "job_cli", "Step-1_0.vtu"))
            )
            self.assertTrue(
                os.path.isfile(os.path.join(directory, "job_cli", "job_cli.csv"))
            )
        self.assertTrue(source.closed)
        self.assertEqual(source.close_calls, 1)

    def test_header_and_pvd_only_exits_close_source(self):
        for options, expected_code, relative_path in (
            (["--header", "1"], "job_cli", "job_cli.json"),
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
                None,
                os.path.join("job_cli", "job_cli.pvd"),
            ),
        ):
            with self.subTest(
                options=options
            ), tempfile.TemporaryDirectory() as directory:
                source = make_source()
                with self.assertRaises(SystemExit) as result:
                    self.run_cli(directory, source, options)
                if expected_code is None:
                    self.assertIsNone(result.exception.code)
                else:
                    self.assertIn(expected_code, result.exception.code)
                self.assertTrue(os.path.isfile(os.path.join(directory, relative_path)))
                self.assertTrue(source.closed)
                self.assertEqual(source.close_calls, 1)

    def test_missing_selection_exit_closes_source(self):
        source = make_source()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit) as result:
                self.run_cli(directory, source, ["--header", "0"])
        self.assertEqual(result.exception.code, "instance not found")
        self.assertTrue(source.closed)

    def test_conversion_exception_closes_source(self):
        source = make_source()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SelectionError):
                self.run_cli(
                    directory,
                    source,
                    ["--header", "0", "--instance", "UNKNOWN", "--step", "Step-1:0"],
                )
        self.assertTrue(source.closed)
        self.assertEqual(source.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
