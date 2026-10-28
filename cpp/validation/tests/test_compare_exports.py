"""Positive/negative controls for the migration's semantic comparison tool."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
HAS_VTK = importlib.util.find_spec("vtkmodules") is not None
if HAS_VTK:
    from compare_exports import compare, main
    from odb2vtk_core import writers
    from odb2vtk_core.models import FieldArray, MeshData


@unittest.skipUnless(HAS_VTK, "optional VTK validation environment required")
class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.reference = self.write("reference", 1.0)
        self.report = dict(paths=[str(self.reference)])

    def write(self, folder, value, label="0"):
        path = self.root / folder / "Step-1_0.vtu"
        path.parent.mkdir()
        mesh = MeshData(np.zeros((1, 3)), np.array([0]), np.array([1]), np.array([1]))
        field = FieldArray(
            "TEMP", "PointData", "Scalars", (label,), np.array([[value]])
        )
        with path.open("w") as stream:
            writers.write_vtu(stream, mesh, [field], [])
        return path

    def test_identical_data_passes(self):
        result = compare(self.report, [self.write("same", 1.0)])
        self.assertTrue(result["parity"])
        self.assertEqual(result["frames_checked"], 1)
        self.assertEqual(result["differences"], [])

    def test_value_and_label_changes_are_detected(self):
        result = compare(self.report, [self.write("different", 2.0, "changed")])
        self.assertFalse(result["parity"])
        self.assertEqual(
            {d["kind"] for d in result["differences"]},
            {"array_values", "component_labels"},
        )

    def test_one_ulp_is_recorded_explicitly(self):
        value = float(np.nextafter(np.float32(1.0), np.float32(2.0)))
        result = compare(self.report, [self.write("rounding", value)])
        self.assertTrue(result["parity"])
        self.assertEqual(result["float32_rounding"][0]["differing_values"], 1)

    def test_missing_output_is_not_a_false_pass(self):
        result = compare(self.report, [self.root / "missing.vtu"])
        self.assertFalse(result["parity"])
        self.assertIn("missing_vtu", {d["kind"] for d in result["differences"]})

    def test_strict_cli_returns_failure_but_writes_inventory(self):
        reference = self.root / "reference.json"
        reference.write_text(json.dumps(self.report))
        report = self.root / "inventory.json"
        args = [
            "compare_exports.py",
            "--python-report",
            str(reference),
            "--cpp-vtu",
            str(self.root / "missing.vtu"),
            "--report",
            str(report),
            "--strict",
        ]
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 1)
        self.assertFalse(json.loads(report.read_text())["parity"])

    def test_auxiliary_comparison_ignores_layout_but_preserves_schemas(self):
        candidate = self.write("same", 1.0)
        left, right = self.reference.parent, candidate.parent
        header = {"instances": ["A"], "steps": [["Step-1", ["Step-1-frame-0"]]]}
        for folder in (left, right):
            (folder / "header.json").write_text(json.dumps(header))
            (folder / "history.csv").write_text("value\n1.000000\n")
        (left / "collection.pvd").write_text(
            '<VTKFile type="Collection"><Collection><DataSet timestep="1.0" '
            'part="0" file="Step-1_0.vtu"/></Collection></VTKFile>'
        )
        (right / "collection.pvd").write_text(
            '<VTKFile type="Collection">\n<Collection>\n<DataSet file="Step-1_0.vtu" '
            'part="0" timestep="1"/>\n</Collection>\n</VTKFile>'
        )
        report = dict(
            paths=[
                str(self.reference),
                str(left / "history.csv"),
                str(left / "collection.pvd"),
            ]
        )
        result = compare(
            report,
            [candidate],
            left / "header.json",
            right / "header.json",
            right / "history.csv",
            right / "collection.pvd",
        )
        self.assertTrue(result["parity"], result)

    def test_malformed_collection_is_reported_in_inventory(self):
        candidate = self.write("same", 1.0)
        reference = self.root / "collection.pvd"
        reference.write_text("<VTKFile><Collection/></VTKFile>")
        malformed = self.root / "malformed.pvd"
        malformed.write_text("not XML")
        result = compare(
            dict(paths=[str(self.reference), str(reference)]),
            [candidate],
            cpp_pvd=malformed,
        )
        self.assertFalse(result["parity"])
        self.assertIn(
            "collection_schema_or_values", {d["kind"] for d in result["differences"]}
        )


if __name__ == "__main__":
    unittest.main()
