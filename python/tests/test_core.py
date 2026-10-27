"""Plain-data conversion and format contracts, runnable without Abaqus."""

import io
import json
import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

import numpy as np

PYTHON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PYTHON_DIR)

from odb2vtk_core.fields import place_point_data, quaternions_to_directions
from odb2vtk_core.history import assemble_history_table
from odb2vtk_core.mesh import build_label_maps, build_mesh, vtk_cell_type
from odb2vtk_core.models import (
    CollectionEntry,
    Element,
    FieldArray,
    HistorySeries,
    InstanceLabels,
    InstanceMesh,
    MeshData,
)
from odb2vtk_core import writers


class ImportTests(unittest.TestCase):
    def test_core_imports_without_abaqus(self):
        code = (
            "import sys\n"
            "import importlib.abc\n"
            "sys.path.insert(0, {0!r})\n"
            "class BlockAbaqus(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, fullname, *args):\n"
            '        if fullname in ("odbAccess", "abaqusConstants", "utilities"):\n'
            "            raise ImportError(fullname)\n"
            "sys.meta_path.insert(0, BlockAbaqus())\n"
            "from odb2vtk_core import models, mesh, fields, history, writers\n"
        ).format(PYTHON_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class MeshTests(unittest.TestCase):
    def test_instance_scoped_labels_and_connectivity(self):
        labels = [
            InstanceLabels("A", [20, 10, 30], [7]),
            InstanceLabels("B", [20, 10, 30, 40], [7]),
        ]
        index = build_label_maps(labels)
        self.assertEqual(index.node_map["A"], {20: 0, 10: 1, 30: 2})
        self.assertEqual(index.node_map["B"], {20: 3, 10: 4, 30: 5, 40: 6})
        self.assertEqual(index.element_map, {"A": {7: 0}, "B": {7: 1}})
        self.assertEqual((index.node_count, index.cell_count), (7, 2))
        mesh = build_mesh(
            [
                InstanceMesh(
                    "A",
                    [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                    [Element(7, [30, 20, 10], "S3")],
                ),
                InstanceMesh(
                    "B",
                    [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
                    [Element(7, [20, 10, 30, 40], "S4R")],
                ),
            ],
            index.node_map,
        )
        np.testing.assert_array_equal(mesh.connectivity, [2, 0, 1, 3, 4, 5, 6])
        np.testing.assert_array_equal(mesh.offsets, [3, 7])
        np.testing.assert_array_equal(mesh.cell_types, [5, 9])
        self.assertEqual(mesh.points.shape, (7, 3))
        np.testing.assert_array_equal(mesh.points[3], [0, 0, 1])

    def test_existing_element_families(self):
        for name, expected in (
            ("C3D4", 10),
            ("C3D6", 13),
            ("C3D8R", 12),
            ("C3D10", 24),
            ("C3D15", 26),
            ("C3D20R", 25),
            ("S3", 5),
            ("S4R", 9),
            ("S8R", 23),
            ("S9", 28),
            ("B31", 3),
            ("R3D3", 5),
            ("R3D4", 9),
        ):
            with self.subTest(element=name):
                self.assertEqual(vtk_cell_type(name), expected)
        with self.assertRaisesRegex(ValueError, "UNKNOWN element type not found"):
            vtk_cell_type("UNKNOWN")

    def test_empty_mesh(self):
        mesh = build_mesh([], {})
        self.assertEqual(mesh.points.shape, (0, 3))
        self.assertEqual(mesh.connectivity.size, 0)


class FieldTests(unittest.TestCase):
    def test_nodal_values_follow_labels_and_keep_padding(self):
        values = np.zeros((3, 2))
        result = place_point_data([10, 20], [[1, 2], [3, 4]], {20: 0, 10: 2}, values)
        self.assertIs(result, values)
        np.testing.assert_array_equal(values, [[3, 4], [0, 0], [1, 2]])

    def test_orientation_preserves_existing_quaternion_convention(self):
        half = np.sqrt(0.5)
        values = quaternions_to_directions(
            [[0, 0, 0, 1], [0, 0, half, half], [0, 0, 0, 0], [1, 0, 0, 0]]
        )
        np.testing.assert_allclose(
            values, [[1, 0, 0], [0, -1, 0], [0, 0, 0], [1, 0, 0]]
        )


class WriterTests(unittest.TestCase):
    def test_vtu_preserves_mesh_fields_components_and_active_attributes(self):
        mesh = MeshData(
            np.array([[0, 0, 0], [1, 0, 0]]),
            np.array([1, 0]),
            np.array([2]),
            np.array([3]),
        )
        points = [
            FieldArray(
                "U",
                "PointData",
                "Vectors",
                ("U1", "U2", "U3"),
                np.array([[1, 2, 3], [4, 5, 6]]),
            ),
            FieldArray(
                "RF", "PointData", "Vectors", ("RF1", "RF2", "RF3"), np.zeros((2, 3))
            ),
        ]
        cells = [
            FieldArray(
                "S",
                "CellData",
                "Tensors",
                ("S11", "S22", "S12"),
                np.array([[10, 20, 30]]),
            ),
            FieldArray(
                "Material_Orientation", "CellData", "Vectors", (), np.array([[1, 0, 0]])
            ),
        ]
        stream = io.StringIO()
        writers.write_vtu(stream, mesh, iter(points), iter(cells))
        root = ET.fromstring(stream.getvalue())
        self.assertEqual(root.attrib["version"], "1,0")
        piece = root.find("UnstructuredGrid/Piece")
        self.assertEqual(piece.attrib, {"NumberOfPoints": "2", "NumberOfCells": "1"})
        self.assertEqual(piece.find("PointData").attrib["Vectors"], "'U','RF'")
        displacement = piece.find("PointData/DataArray")
        self.assertEqual(displacement.attrib["ComponentName2"], "U3")
        np.testing.assert_array_equal(
            np.fromstring(displacement.text, sep=" "), [1, 2, 3, 4, 5, 6]
        )
        orientation = piece.find("CellData").findall("DataArray")[1]
        self.assertEqual(orientation.attrib["NumberOfComponents"], "3")
        self.assertNotIn("ComponentName0", orientation.attrib)
        arrays = {
            array.attrib["Name"]: array for array in piece.findall("Cells/DataArray")
        }
        np.testing.assert_array_equal(
            np.fromstring(arrays["connectivity"].text, sep=" "), [1, 0]
        )
        self.assertEqual(arrays["types"].attrib["type"], "Int64")

    def test_pvd_preserves_times_parts_and_relative_filenames(self):
        stream = io.StringIO()
        writers.write_pvd(
            stream,
            [
                CollectionEntry(0.0, 0, "Step-1_0.vtu"),
                CollectionEntry(0.0, 1, "Step-2_0.vtu"),
            ],
        )
        entries = ET.fromstring(stream.getvalue()).findall("Collection/DataSet")
        self.assertEqual(
            entries[0].attrib, {"timestep": "0.0", "part": "0", "file": "Step-1_0.vtu"}
        )
        self.assertEqual(
            entries[1].attrib, {"timestep": "0.0", "part": "1", "file": "Step-2_0.vtu"}
        )

    def test_header_schema(self):
        metadata = {"instances": ["A"], "steps": [["Step-1", ["Step-1-frame-0"]]]}
        stream = io.StringIO()
        writers.write_header(stream, metadata)
        self.assertEqual(json.loads(stream.getvalue()), metadata)

    def test_csv_preserves_format_and_keeps_timestamps_in_series(self):
        series = HistorySeries("Step-1_A_U", [0.1, 0.2], [11, 12])
        table = assemble_history_table([series])
        stream = io.StringIO()
        writers.write_csv(stream, table)
        self.assertEqual(stream.getvalue(), "Step-1_A_U\n11.000000\n12.000000\n")
        self.assertEqual(series.timestamps, [0.1, 0.2])

    def test_empty_history(self):
        table = assemble_history_table([])
        self.assertEqual(table.headers, ())
        self.assertEqual(table.values.shape, (0, 0))


if __name__ == "__main__":
    unittest.main()
