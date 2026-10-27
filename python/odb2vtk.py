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

from odb2vtk_core.fields import (
    place_cell_data,
    place_point_data,
    quaternions_to_directions,
)
from odb2vtk_core.history import assemble_history_table
from odb2vtk_core.mesh import build_label_maps, build_mesh, vtk_cell_type
from odb2vtk_core.models import (
    CollectionEntry,
    FieldArray,
    FieldLayout,
)
from odb2vtk_core import writers
from odb2vtk_core.source import (
    AbaqusSource,
    ReadableOdb,
    legacy_field_layout,
    normalize_bulk_blocks,
)

MATERIAL_ORIENTATION = "Material_Orientation"


def ABAQUS_VTK_CELL_MAP(abaqusElementType):
    # Preserve the existing script helper's failure behavior.
    try:
        return vtk_cell_type(abaqusElementType)
    except ValueError as error:
        sys.exit(str(error))


def ABAQUS_VTK_FIELDOUPUTS_MAP(fldOutput):
    return legacy_field_layout(fldOutput)


class ODB2VTK(object):
    """Coordinate exports through a normalized, injectable source.

    A source opened here is owned and closed here. An injected source remains
    caller-owned. The legacy initialization sequence remains until Phase 3.
    """

    def __init__(self, fileFullName, suffix, source=None):
        self.fileFullName = fileFullName
        self.odbFileName = os.path.basename(fileFullName)
        self.odbFileNameNoExt = self.odbFileName.split(".")[0] + suffix
        self.odbPath = os.path.dirname(fileFullName)
        self._owns_source = source is None
        self._source = (
            AbaqusSource.open(self.fileFullName) if source is None else source
        )
        self._nodes_map = {}
        self._elements_map = {}
        self._instance_names = []
        self._step_frame_map = {}
        self._nodesNum = 0
        self._cellsNum = 0

    @property
    def source(self):
        return self._source

    @property
    def odb(self):
        """Legacy native access; new callers should use source or close()."""
        return ReadableOdb.from_source(self.source)

    def close(self):
        if self._owns_source:
            self.source.close()

    def __enter__(self):
        if self.source.closed:
            raise RuntimeError("ODB source is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def ExtractHeader(self):
        metadata = {"instances": [], "steps": []}
        print("Scan instances...")
        metadata["instances"].extend(self.source.instance_names)
        print("Scan steps and frames...")
        for step in self.source.steps:
            step_name = step.name
            count = step.frame_count
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
            yield self.source.mesh_labels(name)

    def ConstructMap(self):
        index = build_label_maps(self._instance_labels())
        self._nodes_map = index.node_map
        self._elements_map = index.element_map
        self._nodesNum = index.node_count
        self._cellsNum = index.cell_count

    def _instance_meshes(self):
        for name in self._instance_names:
            yield self.source.mesh(name)

    def _assemble_field(self, blocks, layout, name, association):
        size = self._nodesNum if association == "PointData" else self._cellsNum
        values = np.zeros((size, len(layout.component_names)))
        for block in blocks:
            if association == "PointData":
                place_point_data(
                    block.labels,
                    block.values,
                    self._nodes_map[block.instance_name],
                    values,
                )
            else:
                place_cell_data(
                    block.labels,
                    block.values,
                    block.integration_points,
                    self._elements_map[block.instance_name],
                    values,
                )
        return FieldArray(
            name, association, layout.kind, layout.component_names, values
        )

    def _read_field_array(
        self, step, frame, field_name, layout, name, association, section
    ):
        blocks = (
            block
            for instance in self._instance_names
            for block in self.source.field_blocks(
                step, frame, field_name, instance, layout.position, section
            )
        )
        return self._assemble_field(blocks, layout, name, association)

    def _read_field_arrays(self, name, step_name, frame_index):
        info = self.source.describe_field(
            step_name, frame_index, name, self._instance_names
        )
        layout = info.layout
        if layout.position == "NODAL":
            requests = [(layout, name, "PointData")]
        elif layout.position == "INTEGRATION_POINT":
            requests = [
                (layout._replace(position="CENTROID"), name + "_Centroid", "CellData"),
                (
                    layout._replace(
                        component_names=layout.component_names
                        * info.max_integration_point
                    ),
                    name + "_IntegrationPoints",
                    "CellData",
                ),
            ]
        else:
            # Position support is unchanged by the source extraction.
            return
        for output_layout, output_name, association in requests:
            for section in info.section_points or (None,):
                section_name = (
                    output_name
                    if section is None
                    else output_name + section.description
                )
                yield self._read_field_array(
                    step_name,
                    frame_index,
                    name,
                    output_layout,
                    section_name,
                    association,
                    section,
                )

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
        for description, section in (
            sectionPointMap.items() if sectionPointMap else [("", None)]
        ):
            field = self._legacy_field_array(
                fldOutput,
                FieldLayout(*vtkData),
                fldName + description,
                dataType,
                section,
            )
            self._append_legacy_array(field, data_map, buffer)
        return buffer

    def _legacy_field_array(self, field, layout, name, association, section=None):
        blocks = (
            block
            for instance in self._instance_names
            for block in self.source.legacy_field_blocks(
                field, instance, layout.position, section
            )
        )
        return self._assemble_field(blocks, layout, name, association)

    def WriteDataArray(self, fldOutput, vtkData, description, dataType, buffer=None):
        if buffer is None:
            buffer = []
        field = self._legacy_field_array(
            fldOutput, FieldLayout(*vtkData), description, dataType
        )
        stream = io.StringIO()
        writers.write_data_array(stream, field)
        buffer.append(stream.getvalue())
        return buffer

    def WriteSortedPointData(self, bulkDataBlocks, instanceName, pointDataArray):
        for block in normalize_bulk_blocks(bulkDataBlocks, instanceName, "NODAL"):
            place_point_data(
                block.labels,
                block.values,
                self._nodes_map[instanceName],
                pointDataArray,
            )

    def WriteSortedCellData(self, bulkDataBlocks, instanceName, cellDataArray):
        for block in normalize_bulk_blocks(bulkDataBlocks, instanceName, "CENTROID"):
            place_cell_data(
                block.labels,
                block.values,
                block.integration_points,
                self._elements_map[instanceName],
                cellDataArray,
            )

    def _read_local_cs(self, name, step_name, frame_index):
        if "S" not in self.source.field_names(step_name, frame_index):
            return None
        quaternions = np.zeros((self._cellsNum, 4))
        for block in self.source.orientation_blocks(
            step_name, frame_index, self._instance_names
        ):
            place_point_data(
                block.labels,
                block.quaternions,
                self._elements_map[block.instance_name],
                quaternions[:, : block.quaternions.shape[1]],
            )
        return FieldArray(
            name, "CellData", "Vectors", (), quaternions_to_directions(quaternions)
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
        for name in self.source.field_names(step_name, frame_index):
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
                        self.source.frame_time(step_name, frame_index),
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
            for series in self.source.history(step_name):
                yield series

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

    with ODB2VTK(args.odbFile, args.suffix) as odb2vtk:
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
