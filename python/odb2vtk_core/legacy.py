"""Compatibility facade delegating the former ODB2VTK interface to Converter."""

import io
import os
import sys

from .converter import Converter, MATERIAL_ORIENTATION
from .errors import SelectionError
from .fields import place_cell_data, place_point_data
from .mesh import vtk_cell_type
from .models import FieldLayout, Selection
from .outputs import OutputOptions, ensure_directory
from .source import (
    AbaqusSource,
    ReadableOdb,
    legacy_field_layout,
    normalize_bulk_blocks,
)
from . import writers


def ABAQUS_VTK_CELL_MAP(abaqusElementType):
    try:
        return vtk_cell_type(abaqusElementType)
    except ValueError as error:
        sys.exit(str(error))


def ABAQUS_VTK_FIELDOUPUTS_MAP(fldOutput):
    return legacy_field_layout(fldOutput)


def _console_progress(event):
    print("{0} file completed.".format(event.path))


class ODB2VTK(object):
    """Preserve script/library entry points while Converter owns export logic."""

    def __init__(self, fileFullName, suffix, source=None):
        self.fileFullName = fileFullName
        self.odbFileName = os.path.basename(fileFullName)
        self.odbPath = os.path.dirname(fileFullName)
        self._outputs = OutputOptions.from_odb(fileFullName, suffix, write_pvd=False)
        self.odbFileNameNoExt = self._outputs.run_name
        self._owns_source = source is None
        source = AbaqusSource.open(fileFullName) if source is None else source
        self._converter = Converter(source, progress=_console_progress)
        self._selection = None
        self._legacy_prepared = None

    @property
    def source(self):
        return self._converter.source

    @property
    def odb(self):
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

    def ReadArgs(self, instanceNames, stepsFramesDict):
        self._selection = Selection(instanceNames, stepsFramesDict)
        self._legacy_prepared = None

    def _selected(self):
        if self._selection is None:
            raise SelectionError(
                "Provide a selection with ReadArgs before legacy export"
            )
        return self._selection

    def ConstructMap(self):
        selection = self._converter._validate_selection(
            self._selected(), require_frames=True
        )
        self._legacy_prepared = self._converter._prepare_mesh(selection)

    def _prepared(self):
        if self._legacy_prepared is None:
            self.ConstructMap()
        return self._legacy_prepared

    def ExtractHeader(self):
        return self._converter.export_header(self._outputs)

    def WriteVTUFiles(self):
        return self._converter.export_frames(self._selected(), self._outputs)

    def WriteVTUFile(self, args):
        step, frame = args
        selection = Selection(self._selected().instances, ((step, (frame,)),))
        return self._converter.export_frames(selection, self._outputs)

    def WritePVDFile(self):
        return self._converter.export_collection(self._selected(), self._outputs)

    def WriteCSVFILE(self):
        return self._converter.export_history(self._selected(), self._outputs)

    def GetExportFileName(self, filName):
        path = self._outputs.artifact_path(filName)
        ensure_directory(self._outputs.data_directory)
        return path

    @staticmethod
    def _append_legacy_array(field, data_map, buffer):
        stream = io.StringIO()
        writers.write_data_array(stream, field)
        buffer.append(stream.getvalue())
        data_map[field.kind].append(field.name)

    def WriteFieldOutputData(
        self, fldName, stepName, frameIdx, pointdata_map, celldata_map
    ):
        prepared = self._prepared()
        plans = self._converter._field_plans(
            stepName,
            frameIdx,
            prepared.instances,
            [],
            names=(fldName,),
            include_orientation=False,
        )
        point_buffer, cell_buffer = [], []
        for plan in plans:
            field = self._converter._read_plan(plan, stepName, frameIdx, prepared)
            if field.association == "PointData":
                self._append_legacy_array(field, pointdata_map, point_buffer)
            else:
                self._append_legacy_array(field, celldata_map, cell_buffer)
        return point_buffer, cell_buffer

    def _legacy_field_array(self, field, layout, name, association, section=None):
        prepared = self._prepared()
        blocks = (
            block
            for instance in prepared.instances
            for block in self.source.legacy_field_blocks(
                field, instance, layout.position, section
            )
        )
        return self._converter._assemble_field(
            blocks, layout, name, association, prepared
        )

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

    def WriteSortedPointData(self, bulkDataBlocks, instanceName, pointDataArray):
        index = self._prepared().index
        for block in normalize_bulk_blocks(bulkDataBlocks, instanceName, "NODAL"):
            place_point_data(
                block.labels, block.values, index.node_map[instanceName], pointDataArray
            )

    def WriteSortedCellData(self, bulkDataBlocks, instanceName, cellDataArray):
        index = self._prepared().index
        for block in normalize_bulk_blocks(bulkDataBlocks, instanceName, "CENTROID"):
            place_cell_data(
                block.labels,
                block.values,
                block.integration_points,
                index.element_map[instanceName],
                cellDataArray,
            )

    def WriteLocalCS(self, fldName, stepName, frameIdx, celldata_map, buffer=None):
        if buffer is None:
            buffer = []
        if "S" in self.source.field_names(stepName, frameIdx):
            field = self._converter._orientation(
                stepName, frameIdx, self._prepared(), fldName
            )
            self._append_legacy_array(field, celldata_map, buffer)
        return buffer
