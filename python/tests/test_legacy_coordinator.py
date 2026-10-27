"""Characterize the retained coordinator with synthetic Abaqus query results.

Import stubs are limited to this integration seam until the source extraction in
Phase 2. Core regression tests import the extracted modules directly.
"""

import contextlib
import csv
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

import numpy as np


class SyntheticField:
    def __init__(self, field_type, components, position, blocks, filters=None):
        self.type = field_type
        self.componentLabels = components
        self.locations = [types.SimpleNamespace(position=position)]
        self.blocks = blocks
        self.filters = filters or {}

    def getSubset(self, **filters):
        combined = dict(self.filters, **filters)
        return SyntheticField(
            self.type,
            self.componentLabels,
            self.locations[0].position,
            self.blocks,
            combined,
        )

    @property
    def bulkDataBlocks(self):
        blocks = []
        for instance, position, block in self.blocks:
            if "region" in self.filters and instance != self.filters["region"].name:
                continue
            if "position" in self.filters and position != self.filters["position"]:
                continue
            if (
                "sectionPoint" in self.filters
                and block.sectionPoint != self.filters["sectionPoint"]
            ):
                continue
            blocks.append(block)
        return blocks


def make_reader(include_stress=True):
    instances = {}
    nodal = []
    scalars = []
    stress = []
    sections = [
        types.SimpleNamespace(description="Top"),
        types.SimpleNamespace(description="Bottom"),
    ]
    for name, offset in (("A", 0), ("B", 100)):
        instances[name] = types.SimpleNamespace(
            name=name,
            nodes=[
                types.SimpleNamespace(label=label, coordinates=(label, offset, 0))
                for label in (3, 1, 4, 2)
            ],
            elements=[
                types.SimpleNamespace(label=7, connectivity=(1, 2, 3, 4), type="S4")
            ],
        )
        for blocks, data in (
            (nodal, [[offset + label, 0, 0] for label in (1, 2, 3, 4)]),
            (scalars, [[offset + label] for label in (1, 2, 3, 4)]),
        ):
            blocks.append(
                (
                    name,
                    "NODAL",
                    types.SimpleNamespace(
                        nodeLabels=np.array([1, 2, 3, 4]),
                        data=np.array(data),
                        sectionPoint=None,
                        integrationPoints=None,
                    ),
                )
            )
        for section_index, section in enumerate(sections):
            base = offset + section_index * 10
            stress.append(
                (
                    name,
                    "INTEGRATION_POINT",
                    types.SimpleNamespace(
                        elementLabels=np.array([7, 7]),
                        integrationPoints=np.array([1, 2]),
                        data=np.array([[base + 1, base + 2], [base + 3, base + 4]]),
                        sectionPoint=section,
                    ),
                )
            )
            stress.append(
                (
                    name,
                    "CENTROID",
                    types.SimpleNamespace(
                        elementLabels=np.array([7]),
                        integrationPoints=None,
                        data=np.array([[base + 90, base + 91]]),
                        sectionPoint=section,
                        localCoordSystem=np.array([[0, 0, 0, 1]]),
                    ),
                )
            )
    fields = {
        "U": SyntheticField("VECTOR", ("U1", "U2", "U3"), "NODAL", nodal),
        "TEMP": SyntheticField("SCALAR", (), "NODAL", scalars),
    }
    if include_stress:
        fields["S"] = SyntheticField(
            "TENSOR", ("S11", "S22"), "INTEGRATION_POINT", stress
        )
    regions = {
        name: types.SimpleNamespace(
            historyOutputs={
                "U": types.SimpleNamespace(data=[(0, value), (1, value + 1)])
            }
        )
        for name, value in (("A", 11), ("B", 21))
    }
    return types.SimpleNamespace(
        getInstancesKeys=["A", "B"],
        getStepsKeys=["Step-1"],
        getFrames=lambda step: [types.SimpleNamespace(frameValue=0.5)],
        getFrame=lambda step, frame: types.SimpleNamespace(frameValue=0.5),
        getInstance=instances.__getitem__,
        getNodes=lambda name: instances[name].nodes,
        getElements=lambda name: instances[name].elements,
        getFieldOutput=lambda step, frame, name: fields[name],
        getFieldOutputs=lambda step, frame: fields.items(),
        getHistoryRegions=lambda step: regions,
    )


class LegacyCoordinatorTests(unittest.TestCase):
    def load_exporter(self, reader):
        constants = types.ModuleType("abaqusConstants")
        for name in ("NODAL", "INTEGRATION_POINT", "CENTROID", "SCALAR", "VECTOR"):
            setattr(constants, name, name)
        utilities = types.ModuleType("utilities")
        utilities.ReadableOdb = Mock(return_value=reader)
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "odb2vtk.py")
        spec = importlib.util.spec_from_file_location(
            "legacy_coordinator_under_test", path
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules, {"abaqusConstants": constants, "utilities": utilities}
        ):
            spec.loader.exec_module(module)
        return module

    def test_exports_preserve_selection_sections_centroid_queries_and_schemas(self):
        module = self.load_exporter(make_reader())
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(
            io.StringIO()
        ):
            converter = module.ODB2VTK(os.path.join(directory, "job.odb"), "_case")
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
        module = self.load_exporter(make_reader(include_stress=False))
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(
            io.StringIO()
        ):
            converter = module.ODB2VTK(os.path.join(directory, "job.odb"), "")
            converter.ReadArgs(["A"], {"Step-1": [0]})
            converter.ConstructMap()
            converter.WriteVTUFiles()
            piece = ET.parse(os.path.join(directory, "job", "Step-1_0.vtu")).find(
                "UnstructuredGrid/Piece"
            )
            self.assertEqual(piece.attrib["NumberOfPoints"], "4")
            self.assertEqual(piece.findall("CellData/DataArray"), [])

    def test_legacy_field_method_delegates_to_the_same_conversion_and_writer(self):
        module = self.load_exporter(make_reader())
        converter = module.ODB2VTK("job.odb", "")
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
