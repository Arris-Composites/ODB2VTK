"""Cohesive export operations over an injected, caller-owned source."""

from collections import namedtuple
import os

import numpy as np

from . import writers
from .errors import ExportFailure, OutputError, SelectionError, SourceError
from .fields import place_cell_data, place_point_data, quaternions_to_directions
from .history import assemble_history_table
from .mesh import build_label_maps, build_mesh
from .models import (
    CollectionEntry,
    Diagnostic,
    ExportResult,
    FieldArray,
    FrameExport,
    ProgressEvent,
    Selection,
)
from .outputs import OutputOptions, atomic_output, validate_destinations

MATERIAL_ORIENTATION = "Material_Orientation"
_PreparedMesh = namedtuple("_PreparedMesh", "instances index mesh")
_FieldPlan = namedtuple(
    "_FieldPlan", "name association kind component_names source_name position section"
)


class Converter(object):
    """Borrow a source and export complete requests without setup-order rules."""

    def __init__(self, source, progress=None):
        if progress is not None and not callable(progress):
            raise ValueError("Progress reporting must be callable")
        self._source = source
        self._progress = progress

    @property
    def source(self):
        return self._source

    def _check_open(self):
        if self.source.closed:
            raise SourceError("ODB source is closed")

    def inspect(self):
        self._check_open()
        try:
            instances = list(self.source.instance_names)
            steps = tuple(self.source.steps)
        except Exception as error:
            raise SourceError("Cannot read source metadata: {0}".format(error))
        return {
            "instances": instances,
            "steps": [
                [
                    step.name,
                    [
                        step.name
                        + "-frame-{0}".format(str(i).zfill(len(str(step.frame_count))))
                        for i in range(step.frame_count)
                    ],
                ]
                for step in steps
            ],
        }

    def _validate_selection(self, selection, require_frames):
        if not isinstance(selection, Selection):
            raise SelectionError("Provide a Selection instance")
        # Reconstruct to recheck records made with low-level namedtuple helpers.
        selection = Selection(selection.instances, selection.steps)
        self._check_open()
        if require_frames and not selection.instances:
            raise SelectionError("Select at least one instance for frame export")
        try:
            names = set(self.source.instance_names) if selection.instances else set()
            steps = {step.name: step.frame_count for step in self.source.steps}
        except Exception as error:
            raise SourceError("Cannot read source metadata: {0}".format(error))
        if selection.instances:
            for name in selection.instances:
                if name not in names:
                    raise SelectionError("Instance not found: {0}".format(name))
        for name, frames in selection.steps:
            if name not in steps:
                raise SelectionError("Step not found: {0}".format(name))
            if require_frames and not frames:
                raise SelectionError(
                    "Select at least one frame for step {0}".format(name)
                )
            for frame in frames:
                if frame >= steps[name]:
                    raise SelectionError(
                        "Frame {0} is out of range for step {1}".format(frame, name)
                    )
        return selection

    @staticmethod
    def _validate_outputs(outputs, paths):
        if not isinstance(outputs, OutputOptions):
            raise OutputError("Provide OutputOptions")
        # Recheck immutable options, including records made with _replace.
        OutputOptions(*outputs)
        validate_destinations(paths)

    def _prepare_mesh(self, selection):
        try:
            labels = tuple(
                self.source.mesh_labels(name) for name in selection.instances
            )
            for instance in labels:
                if len(set(instance.node_labels)) != len(instance.node_labels) or len(
                    set(instance.element_labels)
                ) != len(instance.element_labels):
                    raise SourceError("Mesh labels must be unique within each instance")
            index = build_label_maps(labels)
            meshes = tuple(self.source.mesh(name) for name in selection.instances)
            for expected, names, mesh in zip(selection.instances, labels, meshes):
                if (
                    names.name != expected
                    or names.name != mesh.name
                    or len(names.node_labels) != len(mesh.coordinates)
                    or tuple(e.label for e in mesh.elements)
                    != tuple(names.element_labels)
                ):
                    raise SourceError(
                        "Mesh geometry and labels disagree for {0}".format(names.name)
                    )
            geometry = build_mesh(meshes, index.node_map)
            return _PreparedMesh(selection.instances, index, geometry)
        except SourceError:
            raise
        except Exception as error:
            raise SourceError("Cannot prepare selected mesh: {0}".format(error))

    def _field_plans(
        self, step, frame, instances, diagnostics, names=None, include_orientation=True
    ):
        plans = []
        names = self.source.field_names(step, frame) if names is None else names
        for name in names:
            info = self.source.describe_field(step, frame, name, instances)
            layout = info.layout
            if layout.position == "NODAL":
                requests = [(name, "PointData", layout)]
            elif layout.position == "INTEGRATION_POINT":
                requests = [
                    (
                        name + "_Centroid",
                        "CellData",
                        layout._replace(position="CENTROID"),
                    ),
                    (
                        name + "_IntegrationPoints",
                        "CellData",
                        layout._replace(
                            component_names=layout.component_names
                            * info.max_integration_point
                        ),
                    ),
                ]
            else:
                diagnostics.append(
                    Diagnostic(
                        step,
                        frame,
                        name,
                        "Unsupported field position: " + layout.position,
                    )
                )
                continue
            for output_name, association, output_layout in requests:
                for section in info.section_points or (None,):
                    plans.append(
                        _FieldPlan(
                            (
                                output_name
                                if section is None
                                else output_name + section.description
                            ),
                            association,
                            output_layout.kind,
                            output_layout.component_names,
                            name,
                            output_layout.position,
                            section,
                        )
                    )
        if include_orientation and "S" in names:
            plans.append(
                _FieldPlan(
                    MATERIAL_ORIENTATION, "CellData", "Vectors", (), None, None, None
                )
            )
        return tuple(plans)

    @staticmethod
    def _assemble_field(blocks, layout, name, association, prepared):
        index = prepared.index
        rows = index.node_count if association == "PointData" else index.cell_count
        values = np.zeros((rows, len(layout.component_names)))
        for block in blocks:
            if association == "PointData":
                place_point_data(
                    block.labels,
                    block.values,
                    index.node_map[block.instance_name],
                    values,
                )
            else:
                place_cell_data(
                    block.labels,
                    block.values,
                    block.integration_points,
                    index.element_map[block.instance_name],
                    values,
                )
        return FieldArray(
            name, association, layout.kind, layout.component_names, values
        )

    def _orientation(self, step, frame, prepared, name=MATERIAL_ORIENTATION):
        values = np.zeros((prepared.index.cell_count, 4))
        for block in self.source.orientation_blocks(step, frame, prepared.instances):
            place_point_data(
                block.labels,
                block.quaternions,
                prepared.index.element_map[block.instance_name],
                values[:, : block.quaternions.shape[1]],
            )
        return FieldArray(
            name, "CellData", "Vectors", (), quaternions_to_directions(values)
        )

    def _read_plan(self, plan, step, frame, prepared):
        if plan.source_name is None:
            return self._orientation(step, frame, prepared, plan.name)
        blocks = (
            block
            for instance in prepared.instances
            for block in self.source.field_blocks(
                step, frame, plan.source_name, instance, plan.position, plan.section
            )
        )
        return self._assemble_field(blocks, plan, plan.name, plan.association, prepared)

    def _write_frame(self, stream, step, frame, prepared, diagnostics):
        plans = self._field_plans(step, frame, prepared.instances, diagnostics)
        points = tuple(plan for plan in plans if plan.association == "PointData")
        cells = tuple(plan for plan in plans if plan.association == "CellData")
        writers.write_vtu(
            stream,
            prepared.mesh,
            (self._read_plan(plan, step, frame, prepared) for plan in points),
            (self._read_plan(plan, step, frame, prepared) for plan in cells),
            point_metadata=points,
            cell_metadata=cells,
        )

    def _report(self, kind, path, completed, total):
        if self._progress is not None:
            self._progress(ProgressEvent(kind, path, completed, total))

    @staticmethod
    def _result(paths, frames, diagnostics):
        return ExportResult(tuple(paths), tuple(frames), tuple(diagnostics))

    @staticmethod
    def _publish_collection(frames, outputs):
        entries = [
            CollectionEntry(frame.timestep, part, os.path.basename(frame.path))
            for part, frame in enumerate(frames)
        ]
        with atomic_output(outputs.collection_path) as stream:
            writers.write_pvd(stream, entries)

    def validate_frames(self, selection, outputs):
        """Validate a complete frame request without mesh reads or file creation."""
        selection = self._validate_selection(selection, require_frames=True)
        if not isinstance(outputs, OutputOptions):
            raise OutputError("Provide OutputOptions")
        targets = tuple(
            outputs.frame_path(step, frame)
            for step, frames in selection.steps
            for frame in frames
        )
        self._validate_outputs(
            outputs, targets + ((outputs.collection_path,) if outputs.write_pvd else ())
        )
        return selection

    def export_frames(self, selection, outputs):
        selection = self.validate_frames(selection, outputs)
        total = sum(len(frames) for _, frames in selection.steps)
        paths, completed, diagnostics = [], [], []
        try:
            prepared = self._prepare_mesh(selection)
            for step, frames in selection.steps:
                for frame in frames:
                    path = outputs.frame_path(step, frame)
                    timestep = self.source.frame_time(step, frame)
                    with atomic_output(path) as stream:
                        self._write_frame(stream, step, frame, prepared, diagnostics)
                    paths.append(path)
                    completed.append(FrameExport(step, frame, timestep, path))
                    self._report("frame_completed", path, len(completed), total)
            if outputs.write_pvd:
                self._publish_collection(completed, outputs)
                paths.append(outputs.collection_path)
                self._report(
                    "collection_completed",
                    outputs.collection_path,
                    len(completed),
                    total,
                )
        except Exception as error:
            raise ExportFailure(
                "Frame export failed: {0}".format(error),
                self._result(paths, completed, diagnostics),
                error,
            )
        return self._result(paths, completed, diagnostics)

    def validate_history(self, selection, outputs):
        """Validate history selection and destination without building a table."""
        selection = self._validate_selection(selection, require_frames=False)
        if not isinstance(outputs, OutputOptions):
            raise OutputError("Provide OutputOptions")
        self._validate_outputs(outputs, (outputs.history_path,))
        return selection

    def export_history(self, selection, outputs):
        selection = self.validate_history(selection, outputs)
        paths = []
        try:
            series = (
                item
                for step, _ in selection.steps
                for item in self.source.history(step)
            )
            table = assemble_history_table(series)
            with atomic_output(outputs.history_path) as stream:
                writers.write_csv(stream, table)
            paths.append(outputs.history_path)
            self._report("history_completed", outputs.history_path, 1, 1)
        except Exception as error:
            raise ExportFailure(
                "History export failed: {0}".format(error),
                self._result(paths, [], []),
                error,
            )
        return self._result(paths, [], [])

    def export_header(self, outputs):
        if not isinstance(outputs, OutputOptions):
            raise OutputError("Provide OutputOptions")
        self._validate_outputs(outputs, (outputs.header_path,))
        paths = []
        try:
            metadata = self.inspect()
            with atomic_output(outputs.header_path) as stream:
                writers.write_header(stream, metadata)
            paths.append(outputs.header_path)
            self._report("header_completed", outputs.header_path, 1, 1)
        except Exception as error:
            raise ExportFailure(
                "Header export failed: {0}".format(error),
                self._result(paths, [], []),
                error,
            )
        return self._result(paths, [], [])

    def validate_collection(self, selection, outputs):
        """Validate collection metadata and require all referenced files to exist."""
        selection = self.validate_frames(selection, outputs)
        frames = tuple(
            FrameExport(
                step,
                frame,
                self.source.frame_time(step, frame),
                outputs.frame_path(step, frame),
            )
            for step, indices in selection.steps
            for frame in indices
        )
        self._validate_outputs(outputs, (outputs.collection_path,))
        missing = [frame.path for frame in frames if not os.path.isfile(frame.path)]
        if missing:
            raise OutputError(
                "Cannot write collection; VTU file is missing: {0}".format(missing[0])
            )
        return frames

    def export_collection(self, selection, outputs):
        """Index existing VTUs; refuse missing references and publish atomically."""
        frames = self.validate_collection(selection, outputs)
        paths = []
        try:
            self._publish_collection(frames, outputs)
            paths.append(outputs.collection_path)
            self._report(
                "collection_completed",
                outputs.collection_path,
                len(frames),
                len(frames),
            )
        except Exception as error:
            raise ExportFailure(
                "Collection export failed: {0}".format(error),
                self._result(paths, [], []),
                error,
            )
        return self._result(paths, [], [])
