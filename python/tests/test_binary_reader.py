"""Optional VTK reader validation of binary geometry, fields and metadata."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odb2vtk_core import Converter, OutputOptions, Selection, binary_writer
from odb2vtk_core.models import FieldArray, MeshData
from test_converter import two_frame_source


@unittest.skipUnless(
    importlib.util.find_spec("vtkmodules"), "optional VTK reader not installed"
)
class BinaryReaderTests(unittest.TestCase):
    def read(self, path):
        from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader

        reader = vtkXMLUnstructuredGridReader()
        messages = []
        reader.AddObserver("ErrorEvent", lambda *args: messages.append(args[1]))
        reader.AddObserver("WarningEvent", lambda *args: messages.append(args[1]))
        reader.SetFileName(str(path))
        reader.Update()
        self.assertEqual(messages, [])
        self.assertEqual(reader.GetErrorCode(), 0)
        return reader.GetOutput()

    def test_two_frame_exports_match_ascii_including_metadata_and_connectivity(self):
        from vtkmodules.util.numpy_support import vtk_to_numpy

        with tempfile.TemporaryDirectory() as directory:
            source = two_frame_source()
            self.addCleanup(source.close)
            converter = Converter(source)
            selection = Selection(["B", "A"], {"Step-1": [1, 0]})
            results = [
                converter.export_frames(
                    selection, OutputOptions(directory, kind, vtu_format=kind)
                )
                for kind in ("ascii", "binary")
            ]
            for a, b in zip(results[0].frames, results[1].frames):
                self.assertEqual((a.timestep, a.frame), (b.timestep, b.frame))
                x, y = self.read(a.path), self.read(b.path)
                np.testing.assert_array_equal(
                    vtk_to_numpy(x.GetPoints().GetData()),
                    vtk_to_numpy(y.GetPoints().GetData()),
                )
                for accessor in ("GetConnectivityArray", "GetOffsetsArray"):
                    np.testing.assert_array_equal(
                        vtk_to_numpy(getattr(x.GetCells(), accessor)()),
                        vtk_to_numpy(getattr(y.GetCells(), accessor)()),
                    )
                self.assertEqual(
                    [x.GetCellType(i) for i in range(x.GetNumberOfCells())],
                    [y.GetCellType(i) for i in range(y.GetNumberOfCells())],
                )
                for association in ("GetPointData", "GetCellData"):
                    left, right = getattr(x, association)(), getattr(y, association)()
                    self.assertEqual(
                        left.GetNumberOfArrays(), right.GetNumberOfArrays()
                    )
                    for i in range(left.GetNumberOfArrays()):
                        old, new = left.GetArray(i), right.GetArray(i)
                        self.assertEqual(old.GetName(), new.GetName())
                        self.assertEqual(old.GetDataType(), new.GetDataType())
                        self.assertEqual(
                            old.GetNumberOfComponents(), new.GetNumberOfComponents()
                        )
                        np.testing.assert_array_equal(
                            vtk_to_numpy(old), vtk_to_numpy(new)
                        )
                        for j in range(old.GetNumberOfComponents()):
                            self.assertEqual(
                                old.GetComponentName(j), new.GetComponentName(j)
                            )
                    for active in ("GetScalars", "GetVectors", "GetTensors"):
                        old, new = getattr(left, active)(), getattr(right, active)()
                        self.assertEqual(
                            None if old is None else old.GetName(),
                            None if new is None else new.GetName(),
                        )

    def test_numeric_types_special_values_and_wide_arrays(self):
        from vtkmodules.util.numpy_support import vtk_to_numpy

        geometry = MeshData(
            np.array([[0.0, -0.0, 1e-100], [1.0, 0.0, 1.0]]),
            np.array([0, 1]),
            np.array([2]),
            np.array([3]),
        )
        special = np.array([0.0, -0.0, np.inf, -np.inf, np.nan, 1.234567890123])
        fields = []
        for width in (1, 2, 3, 6, 9, 48):
            fields.append(
                FieldArray(
                    'field & "方向" {0}'.format(width),
                    "PointData",
                    "Tensors" if width == 9 else "Vectors",
                    tuple('component & "{0}"'.format(i) for i in range(width)),
                    np.resize(special, (2, width)),
                )
            )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "special.vtu"
            with path.open("wb") as stream:
                binary_writer.write_vtu(stream, geometry, fields, [])
            grid = self.read(path)
            self.assertEqual(vtk_to_numpy(grid.GetPoints().GetData()).dtype, np.float64)
            for field in fields:
                array = grid.GetPointData().GetArray(field.name)
                actual = vtk_to_numpy(array).reshape(2, -1)
                expected = field.values.astype(np.float32)
                self.assertEqual(actual.dtype, np.float32)
                np.testing.assert_array_equal(actual, expected)
                np.testing.assert_array_equal(np.signbit(actual), np.signbit(expected))
                for i, label in enumerate(field.component_names):
                    self.assertEqual(array.GetComponentName(i), label)
            self.assertEqual(grid.GetPointData().GetTensors().GetName(), fields[4].name)
            self.assertEqual(grid.GetPointData().GetVectors().GetName(), fields[2].name)

    def test_empty_mesh_loads_without_errors(self):
        geometry = MeshData(
            np.empty((0, 3)),
            np.array([], dtype=int),
            np.array([], dtype=int),
            np.array([], dtype=int),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.vtu"
            with path.open("wb") as stream:
                binary_writer.write_vtu(stream, geometry, [], [])
            grid = self.read(path)
            self.assertEqual(grid.GetNumberOfPoints(), 0)
            self.assertEqual(grid.GetNumberOfCells(), 0)


if __name__ == "__main__":
    unittest.main()
