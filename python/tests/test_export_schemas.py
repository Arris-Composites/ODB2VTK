"""Export characterization through a normally constructed, injected source."""

import csv
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core import Converter, OutputOptions, Selection
from support import make_source


class ExportSchemaTests(unittest.TestCase):
    def test_exports_preserve_selection_sections_centroid_queries_and_schemas(self):
        source = make_source()
        self.addCleanup(source.close)
        with tempfile.TemporaryDirectory() as directory:
            converter = Converter(source)
            selection = Selection(["A", "B"], {"Step-1": [0]})
            outputs = OutputOptions(directory, "job", "_case")
            converter.export_header(outputs)
            converter.export_frames(selection, outputs)
            converter.export_history(selection, outputs)
            output = os.path.join(directory, "job_case")
            piece = ET.parse(os.path.join(output, "Step-1_0.vtu")).find(
                "UnstructuredGrid/Piece"
            )
            self.assertEqual(
                piece.attrib, {"NumberOfPoints": "8", "NumberOfCells": "2"}
            )
            point_arrays = {
                array.attrib["Name"]: array
                for array in piece.findall("PointData/DataArray")
            }
            np.testing.assert_array_equal(
                np.fromstring(point_arrays["TEMP"].text, sep=" "),
                [3, 1, 4, 2, 103, 101, 104, 102],
            )
            self.assertEqual(point_arrays["TEMP"].attrib["ComponentName0"], "0")
            cell_arrays = {
                array.attrib["Name"]: array
                for array in piece.findall("CellData/DataArray")
            }
            self.assertEqual(
                set(cell_arrays),
                {
                    "S_CentroidTop",
                    "S_CentroidBottom",
                    "S_IntegrationPointsTop",
                    "S_IntegrationPointsBottom",
                    "Material_Orientation",
                },
            )
            np.testing.assert_array_equal(
                np.fromstring(cell_arrays["S_CentroidTop"].text, sep=" "),
                [90, 91, 190, 191],
            )
            np.testing.assert_array_equal(
                np.fromstring(cell_arrays["S_IntegrationPointsBottom"].text, sep=" "),
                [11, 12, 13, 14, 111, 112, 113, 114],
            )
            np.testing.assert_array_equal(
                np.fromstring(cell_arrays["Material_Orientation"].text, sep=" "),
                [1, 0, 0, 1, 0, 0],
            )
            with open(os.path.join(directory, "job_case.json")) as stream:
                self.assertEqual(
                    json.load(stream),
                    {
                        "instances": ["A", "B"],
                        "steps": [["Step-1", ["Step-1-frame-0"]]],
                    },
                )
            entry = ET.parse(os.path.join(output, "job_case.pvd")).find(
                "Collection/DataSet"
            )
            self.assertEqual(
                entry.attrib, {"timestep": "0.5", "part": "0", "file": "Step-1_0.vtu"}
            )
            with open(os.path.join(output, "job_case.csv"), newline="") as stream:
                self.assertEqual(
                    list(csv.reader(stream)),
                    [
                        ["Step-1_A_U", "Step-1_B_U"],
                        ["11.000000", "21.000000"],
                        ["12.000000", "22.000000"],
                    ],
                )

    def test_missing_stress_keeps_orientation_optional(self):
        source = make_source(include_stress=False)
        self.addCleanup(source.close)
        with tempfile.TemporaryDirectory() as directory:
            Converter(source).export_frames(
                Selection(["A"], {"Step-1": [0]}), OutputOptions(directory, "job")
            )
            piece = ET.parse(os.path.join(directory, "job", "Step-1_0.vtu")).find(
                "UnstructuredGrid/Piece"
            )
            self.assertEqual(piece.attrib["NumberOfPoints"], "4")
            self.assertEqual(piece.findall("CellData/DataArray"), [])

    def test_single_frame_export_requires_only_a_complete_request(self):
        source = make_source()
        self.addCleanup(source.close)
        with tempfile.TemporaryDirectory() as directory:
            result = Converter(source).export_frames(
                Selection(["A"], {"Step-1": [0]}), OutputOptions(directory, "job")
            )
            field = ET.parse(result.frames[0].path).find(
                'UnstructuredGrid/Piece/PointData/DataArray[@Name="TEMP"]'
            )
            np.testing.assert_array_equal(
                np.fromstring(field.text, sep=" "), [3, 1, 4, 2]
            )


if __name__ == "__main__":
    unittest.main()
