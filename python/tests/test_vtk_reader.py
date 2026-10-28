"""Optional reader checks; VTK is a validation dependency, never a runtime one."""

import importlib.util
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core import Converter, OutputOptions, Selection
from odb2vtk_core.models import FieldArray, MeshData
from odb2vtk_core import writers
from support import make_source


@unittest.skipUnless(
    importlib.util.find_spec("vtkmodules"), "optional VTK reader not installed"
)
class VtkReaderTests(unittest.TestCase):
    def read(self, path):
        from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader

        reader = vtkXMLUnstructuredGridReader()
        messages = []
        reader.AddObserver("ErrorEvent", lambda *args: messages.append(args[1]))
        reader.AddObserver("WarningEvent", lambda *args: messages.append(args[1]))
        reader.SetFileName(path)
        reader.Update()
        self.assertEqual(messages, [])
        self.assertEqual(reader.GetErrorCode(), 0)
        return reader.GetOutput()

    def test_complete_export_loads_geometry_arrays_and_active_fields(self):
        with make_source() as source, tempfile.TemporaryDirectory() as directory:
            result = Converter(source).export_frames(
                Selection(["A", "B"], {"Step-1": [0]}), OutputOptions(directory, "job")
            )
            grid = self.read(result.frames[0].path)
            self.assertEqual(
                (grid.GetNumberOfPoints(), grid.GetNumberOfCells()), (8, 2)
            )
            self.assertEqual(grid.GetCellType(0), 9)
            self.assertEqual(grid.GetPointData().GetVectors().GetName(), "U")
            self.assertEqual(grid.GetPointData().GetScalars().GetName(), "TEMP")
            self.assertEqual(
                grid.GetCellData().GetVectors().GetName(), "Material_Orientation"
            )
            self.assertIsNone(grid.GetCellData().GetTensors())
            self.assertIsNotNone(grid.GetCellData().GetArray("S_CentroidTop"))
            values = grid.GetPointData().GetArray("TEMP")
            self.assertEqual(
                [values.GetValue(i) for i in range(8)], [3, 1, 4, 2, 103, 101, 104, 102]
            )

    def test_xml_names_components_and_nine_component_tensors_round_trip(self):
        name = 'stress & "local" <tensor>'
        labels = tuple('component & "{0}"'.format(i) for i in range(9))
        mesh = MeshData(
            np.array([[0, 0, 0], [1, 0, 0]]),
            np.array([0, 1]),
            np.array([2]),
            np.array([3]),
        )
        field = FieldArray(
            name, "CellData", "Tensors", labels, np.arange(9).reshape(1, 9)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "job.vtu")
            with open(path, "w") as stream:
                writers.write_vtu(stream, mesh, [], [field])
            tensor = self.read(path).GetCellData().GetTensors()
            self.assertEqual(tensor.GetName(), name)
            self.assertEqual(tensor.GetComponentName(8), labels[8])
            self.assertEqual(tensor.GetTuple(0), tuple(range(9)))


if __name__ == "__main__":
    unittest.main()
