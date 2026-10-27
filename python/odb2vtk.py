# /*=========================================================================
#    Program: ODB2VTK
#    Module:  odb2vtk.py
#    Copyright (c) Arris Composites Inc.
#    All rights reserved.
#
#    Arris Composites Inc.
#    745 Heinz Ave
#    Berkeley, CA 94710
#    USA
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ========================================================================*/

# ODB2VTK class to access the data inside odb file and write it into vtu

import argparse
import io
import os
import sys
import timeit

import numpy as np
import utilities
from abaqusConstants import NODAL, INTEGRATION_POINT, CENTROID, SCALAR, VECTOR

from odb2vtk_core.fields import (
    place_cell_data,
    place_point_data,
    quaternions_to_directions,
)
from odb2vtk_core.history import assemble_history_table
from odb2vtk_core.mesh import build_label_maps, build_mesh, vtk_cell_type
from odb2vtk_core.models import (
    CollectionEntry,
    Element,
    FieldArray,
    FieldLayout,
    HistorySeries,
    InstanceLabels,
    InstanceMesh,
)
from odb2vtk_core import writers

MATERIAL_ORIENTATION = "Material_Orientation"


def ABAQUS_VTK_CELL_MAP(abaqusElementType):
    # Preserve the existing script helper's failure behavior.
    try:
        return vtk_cell_type(abaqusElementType)
    except ValueError as error:
        sys.exit(str(error))


def ABAQUS_VTK_FIELDOUPUTS_MAP(fldOutput):
    # FieldLayout is tuple-compatible for existing callers, with named fields
    # for all internal use. Multiple-location handling remains a later change.
    component_names = tuple(fldOutput.componentLabels)
    if fldOutput.type == SCALAR:
        kind = "Scalars"
        if not component_names:
            component_names = ("0",)
    elif fldOutput.type == VECTOR:
        kind = "Vectors"
    else:
        kind = "Tensors"
    return FieldLayout(kind, component_names, fldOutput.locations[0].position)


class ODB2VTK:
    """Coordinate ODB queries using extracted conversion and stream writers.

    Resource ownership and the legacy initialization sequence are intentionally
    retained until the source and converter phases of the refactor.
    """

    def __init__(self, fileFullName, suffix):
        self.fileFullName = fileFullName
        self.odbFileName = os.path.basename(fileFullName)
        self.odbFileNameNoExt = self.odbFileName.split(".")[0] + suffix
        self.odbPath = os.path.dirname(fileFullName)
        self.odb = utilities.ReadableOdb(self.fileFullName)
        self._nodes_map = {}
        self._elements_map = {}
        self._instance_names = []
        self._step_frame_map = {}
        self._nodesNum = 0
        self._cellsNum = 0

    def ExtractHeader(self):
        metadata = {"instances": [], "steps": []}
        print("Scan instances...")
        metadata["instances"].extend(self.odb.getInstancesKeys)
        print("Scan steps and frames...")
        for step_name in self.odb.getStepsKeys:
            count = len(self.odb.getFrames(step_name))
            frames = [
                step_name + "-frame-{0}".format(str(i).zfill(len(str(count))))
                for i in range(count)
            ]
            for frame in frames:
                print(frame)
            metadata["steps"].append([step_name, frames])
        with open(
            os.path.join(self.odbPath, self.odbFileNameNoExt) + ".json", "w"
        ) as stream:
            writers.write_header(stream, metadata)

    def ReadArgs(self, instanceNames, stepsFramesDict):
        self._instance_names = instanceNames
        self._step_frame_map = stepsFramesDict

    def _instance_labels(self):
        for name in self._instance_names:
            yield InstanceLabels(
                name,
                [node.label for node in self.odb.getNodes(name)],
                [element.label for element in self.odb.getElements(name)],
            )

    def ConstructMap(self):
        index = build_label_maps(self._instance_labels())
        self._nodes_map = index.node_map
        self._elements_map = index.element_map
        self._nodesNum = index.node_count
        self._cellsNum = index.cell_count

    def _instance_meshes(self):
        for name in self._instance_names:
            yield InstanceMesh(
                name,
                [tuple(node.coordinates) for node in self.odb.getNodes(name)],
                [
                    Element(element.label, tuple(element.connectivity), element.type)
                    for element in self.odb.getElements(name)
                ],
            )

    def _read_field_array(self, field, layout, name, association):
        size = self._nodesNum if association == "PointData" else self._cellsNum
        values = np.zeros((size, len(layout.component_names)))
        for instance_name in self._instance_names:
            subset = field.getSubset(region=self.odb.getInstance(instance_name))
            subset = subset.getSubset(position=layout.position)
            if association == "PointData":
                self.WriteSortedPointData(subset.bulkDataBlocks, instance_name, values)
            else:
                self.WriteSortedCellData(subset.bulkDataBlocks, instance_name, values)
        return FieldArray(
            name, association, layout.kind, layout.component_names, values
        )

    def _section_arrays(self, section_points, field, layout, name, association):
        if not section_points:
            return [self._read_field_array(field, layout, name, association)]
        return [
            self._read_field_array(
                field.getSubset(sectionPoint=point),
                layout,
                name + description,
                association,
            )
            for description, point in section_points.items()
        ]

    def _read_field_arrays(self, name, step_name, frame_index):
        field = self.odb.getFieldOutput(step_name, frame_index, name)
        layout = ABAQUS_VTK_FIELDOUPUTS_MAP(field)
        section_points = {}
        max_points = 1
        for instance_name in self._instance_names:
            subset = field.getSubset(region=self.odb.getInstance(instance_name))
            subset = subset.getSubset(position=layout.position)
            for block in subset.bulkDataBlocks:
                if block.sectionPoint is not None:
                    section_points[block.sectionPoint.description] = block.sectionPoint
                if block.integrationPoints is not None:
                    max_points = max(max_points, block.integrationPoints.max())

        if layout.position == NODAL:
            return self._section_arrays(
                section_points, field, layout, name, "PointData"
            )
        if layout.position == INTEGRATION_POINT:
            centroid_layout = layout._replace(position=CENTROID)
            integration_layout = layout._replace(
                component_names=layout.component_names * max_points
            )
            return self._section_arrays(
                section_points, field, centroid_layout, name + "_Centroid", "CellData"
            ) + self._section_arrays(
                section_points,
                field,
                integration_layout,
                name + "_IntegrationPoints",
                "CellData",
            )
        # Preserve the currently supported positions during mechanical extraction.
        return []

    @staticmethod
    def _append_legacy_array(field, data_map, buffer):
        stream = io.StringIO()
        writers.write_data_array(stream, field)
        buffer.append(stream.getvalue())
        data_map[field.kind].append(field.name)

    def WriteFieldOutputData(
        self, fldName, stepName, frameIdx, pointdata_map, celldata_map
    ):
        point_buffer = []
        cell_buffer = []
        for field in self._read_field_arrays(fldName, stepName, frameIdx):
            if field.association == "PointData":
                self._append_legacy_array(field, pointdata_map, point_buffer)
            else:
                self._append_legacy_array(field, celldata_map, cell_buffer)
        return point_buffer, cell_buffer

    def WriteDataArrayWithSectionPoints(
        self,
        sectionPointMap,
        fldOutput,
        vtkData,
        fldName,
        data_map,
        dataType,
        buffer=None,
    ):
        if buffer is None:
            buffer = []
        for field in self._section_arrays(
            sectionPointMap, fldOutput, FieldLayout(*vtkData), fldName, dataType
        ):
            self._append_legacy_array(field, data_map, buffer)
        return buffer

    def WriteDataArray(self, fldOutput, vtkData, description, dataType, buffer=None):
        if buffer is None:
            buffer = []
        field = self._read_field_array(
            fldOutput, FieldLayout(*vtkData), description, dataType
        )
        stream = io.StringIO()
        writers.write_data_array(stream, field)
        buffer.append(stream.getvalue())
        return buffer

    def WriteSortedPointData(self, bulkDataBlocks, instanceName, pointDataArray):
        if bulkDataBlocks is not None:
            for block in bulkDataBlocks:
                place_point_data(
                    block.nodeLabels,
                    block.data,
                    self._nodes_map[instanceName],
                    pointDataArray,
                )

    def WriteSortedCellData(self, bulkDataBlocks, instanceName, cellDataArray):
        if bulkDataBlocks is not None:
            for block in bulkDataBlocks:
                place_cell_data(
                    block.elementLabels,
                    block.data,
                    block.integrationPoints,
                    self._elements_map[instanceName],
                    cellDataArray,
                )

    def _read_local_cs(self, name, step_name, frame_index):
        try:
            field = self.odb.getFieldOutput(step_name, frame_index, "S")
        except Exception:
            return None
        section_point = None
        for instance_name in self._instance_names:
            subset = field.getSubset(region=self.odb.getInstance(instance_name))
            subset = subset.getSubset(position=CENTROID)
            for block in subset.bulkDataBlocks:
                section_point = block.sectionPoint
                break
            break
        quaternions = np.zeros((self._cellsNum, 4))
        for instance_name in self._instance_names:
            subset = field.getSubset(region=self.odb.getInstance(instance_name))
            subset = subset.getSubset(position=CENTROID)
            if section_point is not None:
                subset = subset.getSubset(sectionPoint=section_point)
            for block in subset.bulkDataBlocks:
                if block.localCoordSystem is not None:
                    values = block.localCoordSystem
                    place_point_data(
                        block.elementLabels,
                        values,
                        self._elements_map[instance_name],
                        quaternions[:, : len(values[0])],
                    )
        return FieldArray(
            name,
            "CellData",
            "Vectors",
            (),
            quaternions_to_directions(quaternions),
        )

    def WriteLocalCS(self, fldName, stepName, frameIdx, celldata_map, buffer=None):
        if buffer is None:
            buffer = []
        field = self._read_local_cs(fldName, stepName, frameIdx)
        if field is not None:
            self._append_legacy_array(field, celldata_map, buffer)
        return buffer

    def WriteVTUFiles(self):
        for step_name, frames in self._step_frame_map.items():
            for frame_index in frames:
                self.WriteVTUFile([step_name, frame_index])

    def WriteVTUFile(self, args):
        step_name, frame_index = args
        try:
            mesh = build_mesh(self._instance_meshes(), self._nodes_map)
        except ValueError as error:
            sys.exit(str(error))
        print("    writing field data")
        point_fields = []
        cell_fields = []
        for name, _ in self.odb.getFieldOutputs(step_name, frame_index):
            for field in self._read_field_arrays(name, step_name, frame_index):
                if field.association == "PointData":
                    point_fields.append(field)
                else:
                    cell_fields.append(field)
        orientation = self._read_local_cs(MATERIAL_ORIENTATION, step_name, frame_index)
        if orientation is not None:
            cell_fields.append(orientation)
        path = self.GetExportFileName(step_name + "_" + str(frame_index)) + ".vtu"
        with open(path, "w") as stream:
            print("writing {0}...".format(stream.name))
            writers.write_vtu(stream, mesh, point_fields, cell_fields)
        print("Complete.")

    def WritePVDFile(self):
        entries = []
        for step_name, frames in self._step_frame_map.items():
            for frame_index in frames:
                entries.append(
                    CollectionEntry(
                        self.odb.getFrame(step_name, frame_index).frameValue,
                        len(entries),
                        step_name + "_" + str(frame_index) + ".vtu",
                    )
                )
        with open(
            self.GetExportFileName(self.odbFileNameNoExt) + ".pvd", "w"
        ) as stream:
            writers.write_pvd(stream, entries)
            print("{0} file completed.".format(stream.name))

    def _history_series(self):
        for step_name in self._step_frame_map:
            for region_name, region in self.odb.getHistoryRegions(step_name).items():
                for output_name, output in region.historyOutputs.items():
                    yield HistorySeries(
                        step_name + "_" + region_name + "_" + output_name,
                        [row[0] for row in output.data],
                        [row[1] for row in output.data],
                    )

    def WriteCSVFILE(self):
        table = assemble_history_table(self._history_series())
        with open(
            self.GetExportFileName(self.odbFileNameNoExt) + ".csv", "w"
        ) as stream:
            writers.write_csv(stream, table)

    def GetExportFileName(self, filName):
        if not os.path.exists(os.path.join(self.odbPath, self.odbFileNameNoExt)):
            os.mkdir(os.path.join(self.odbPath, self.odbFileNameNoExt))
        return os.path.join(self.odbPath, self.odbFileNameNoExt, filName)


if __name__ == "__main__":
    start_time = timeit.default_timer()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--header",
        required=True,
        type=int,
        help="if 1, extract header information and generate a .json file. Otherwise, generate .vtu file",
    )
    parser.add_argument(
        "--instance",
        help="selected instance names which are separated by whitespace, e.g. 'instanceName1' 'instanceName2'",
        nargs="*",
    )
    parser.add_argument(
        "--step",
        help="selected step names and frames which are separated by whitespace, e.g., 'step1:1,2,3' 'step2:2,3,4'",
        nargs="*",
    )
    parser.add_argument(
        "--writeHistory", default=0, type=int, help="if 1, write history output."
    )
    parser.add_argument(
        "--odbFile", required=True, help="selected odb file (full path name)"
    )
    parser.add_argument("--writePVD", default=0, type=int, help="if 1 write a pvd file")
    parser.add_argument(
        "--suffix", default="", type=str, help="string appended to the file"
    )
    args = parser.parse_args()

    # check odbfile
    if not args.odbFile:
        sys.exit("Need an .odf file as input")
    if not os.path.exists(args.odbFile):
        sys.exit("{0} doesn't exist".format(args.odbFile))

    odb2vtk = ODB2VTK(args.odbFile, args.suffix)
    # if --header is on, ignore all others and extract header information
    if args.header:
        odb2vtk.ExtractHeader()
        sys.exit(
            "{0} generated".format(
                os.path.join(odb2vtk.odbPath, odb2vtk.odbFileNameNoExt)
            )
        )

    if not args.instance:
        sys.exit("instance not found")

    if not args.step:
        sys.exit("steps and frames not found")

    # args.step - ['step1:1,2,3', 'step2:2,3,4']
    # convert step-frame dictionary to {'stepname': [0, 1, 2, 3], 'stepname': [0,1,2]} format
    step_frame_dict = {}
    for item in args.step:
        split = item.split(":")
        step_frame_dict[split[0]] = []
        for i in split[1].split(","):
            step_frame_dict[split[0]].append(int(i))
    odb2vtk.ReadArgs(args.instance, step_frame_dict)
    if args.writeHistory:
        odb2vtk.WriteCSVFILE()
    if args.writePVD:
        odb2vtk.WritePVDFile()
        sys.exit()

    odb2vtk.ConstructMap()
    odb2vtk.WriteVTUFiles()

    print("--- %s seconds ---" % (timeit.default_timer() - start_time))
