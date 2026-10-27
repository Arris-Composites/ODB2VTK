"""Export characterization through a normally constructed, injected source."""

import contextlib
import csv
import io
import json
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk import ODB2VTK
from support import make_source


class CoordinatorTests(unittest.TestCase):
    def test_exports_preserve_selection_sections_centroid_queries_and_schemas(self):
        source = make_source()
        self.addCleanup(source.close)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(
            io.StringIO()
        ):
            converter = ODB2VTK(
                os.path.join(directory, "job.odb"), "_case", source=source
            )
            converter.ReadArgs(["A", "B"], {"Step-1": [0]})
            converter.ConstructMap()
            converter.ExtractHeader()
            converter.WriteVTUFiles()
            converter.WritePVDFile()
            converter.WriteCSVFILE()
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
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(
            io.StringIO()
        ):
            converter = ODB2VTK(os.path.join(directory, "job.odb"), "", source=source)
            converter.ReadArgs(["A"], {"Step-1": [0]})
            converter.ConstructMap()
            converter.WriteVTUFiles()
            piece = ET.parse(os.path.join(directory, "job", "Step-1_0.vtu")).find(
                "UnstructuredGrid/Piece"
            )
            self.assertEqual(piece.attrib["NumberOfPoints"], "4")
            self.assertEqual(piece.findall("CellData/DataArray"), [])

    def test_legacy_field_method_delegates_to_the_same_conversion_and_writer(self):
        source = make_source()
        self.addCleanup(source.close)
        converter = ODB2VTK("job.odb", "", source=source)
        converter.ReadArgs(["A"], {"Step-1": [0]})
        converter.ConstructMap()
        point_map = {"Scalars": [], "Vectors": [], "Tensors": []}
        cell_map = {"Scalars": [], "Vectors": [], "Tensors": []}
        points, cells = converter.WriteFieldOutputData(
            "TEMP", "Step-1", 0, point_map, cell_map
        )
        self.assertEqual(point_map["Scalars"], ["TEMP"])
        self.assertEqual(cells, [])
        np.testing.assert_array_equal(
            np.fromstring(ET.fromstring("".join(points)).text, sep=" "), [3, 1, 4, 2]
        )


if __name__ == "__main__":
    unittest.main()
