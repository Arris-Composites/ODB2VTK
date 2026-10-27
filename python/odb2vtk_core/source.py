"""Abaqus source adapter with explicit ownership and normalized data access.

Abaqus imports are lazy: importing the exporter does not require Abaqus.
Normalized reads return owned arrays or immutable Python records. A caller may
keep these values after the source closes; source queries require an open ODB.
"""

import numpy as np

from .models import (
    Element,
    FieldBlock,
    FieldInfo,
    FieldLayout,
    HistorySeries,
    InstanceLabels,
    InstanceMesh,
    OrientationBlock,
    SectionPoint,
    StepInfo,
)


def _load_abaqus():
    import odbAccess
    import abaqusConstants

    return odbAccess, abaqusConstants


def _field_layout(field, constants):
    components = tuple(field.componentLabels)
    if field.type == constants.SCALAR:
        kind = "Scalars"
        if not components:
            components = ("0",)
    elif field.type == constants.VECTOR:
        kind = "Vectors"
    else:
        kind = "Tensors"
    # Preserve first-location behavior until multiple locations are supported.
    return FieldLayout(kind, components, field.locations[0].position)


def _section_point(point):
    if point is None:
        return None
    return SectionPoint(int(point.number), point.description)


def _copy_rows(labels, values):
    labels = np.array(labels, dtype=np.int64, copy=True)
    values = np.array(values, copy=True)
    if values.ndim == 1:
        values = values.reshape((-1, 1))
    if labels.ndim != 1 or values.ndim != 2 or len(labels) != len(values):
        raise ValueError("Bulk-data labels and value rows must have matching lengths")
    return labels, values


def _normalize_bulk_blocks(blocks, instance_name, position):
    """Snapshot native bulk objects while their backing storage is still valid.

    Used only by the adapter. Each yielded record owns its arrays; no Abaqus
    object crosses into numerical conversion.
    """
    if blocks is None:
        return
    position = str(position)
    for block in blocks:
        labels = block.nodeLabels if position == "NODAL" else block.elementLabels
        labels, values = _copy_rows(labels, block.data)
        points = block.integrationPoints
        if points is not None:
            points = np.array(points, dtype=np.int64, copy=True)
            if points.ndim != 1 or len(points) != len(labels):
                raise ValueError("Integration-point numbers must match bulk-data rows")
        yield FieldBlock(
            instance_name,
            position,
            labels,
            values,
            points,
            _section_point(block.sectionPoint),
        )


class AbaqusSource(object):
    """Own an open ODB and expose only normalized data to conversion code.

    ``open`` is the normal factory. The constructor also accepts an already-open
    native handle and constants, transferring handle ownership to the source.
    This provides a seam for contract tests without replacing Python imports.
    """

    def __init__(self, odb, constants):
        self._odb = odb
        self._constants = constants
        self._frame_cache_key = None
        self._frame_cache = None
        self._field_repository_cache = None
        self._field_cache = {}
        self._section_cache_key = None
        self._section_cache = {}

    @classmethod
    def open(cls, path, read_only=True):
        access, constants = _load_abaqus()
        return cls(access.openOdb(path, readOnly=read_only), constants)

    @property
    def closed(self):
        return self._odb is None

    def _require_odb(self):
        if self.closed:
            raise RuntimeError("ODB source is closed")
        return self._odb

    def close(self):
        odb = self._odb
        self._odb = None
        self._clear_frame_cache()
        if odb is not None:
            odb.close()

    def _clear_frame_cache(self):
        self._field_cache.clear()
        self._field_repository_cache = None
        self._frame_cache = None
        self._frame_cache_key = None
        self._section_cache.clear()
        self._section_cache_key = None

    def __enter__(self):
        self._require_odb()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    @property
    def instance_names(self):
        return tuple(self._require_odb().rootAssembly.instances.keys())

    @property
    def steps(self):
        return tuple(
            StepInfo(name, len(step.frames))
            for name, step in self._require_odb().steps.items()
        )

    def _frame(self, step, frame):
        odb = self._require_odb()
        # Distinguish 0 from 0.0 so a cache hit cannot bypass native index checks.
        key = (step, type(frame), frame)
        if key != self._frame_cache_key:
            # Drop previous handles even if the next native lookup fails.
            self._clear_frame_cache()
            native = odb.steps[step].frames[frame]
            self._frame_cache = native
            self._frame_cache_key = key
        return self._frame_cache

    def frame_time(self, step, frame):
        return self._frame(step, frame).frameValue

    def mesh_labels(self, instance):
        native = self._require_odb().rootAssembly.instances[instance]
        return InstanceLabels(
            instance,
            tuple(node.label for node in native.nodes),
            tuple(element.label for element in native.elements),
        )

    def mesh(self, instance):
        native = self._require_odb().rootAssembly.instances[instance]
        return InstanceMesh(
            instance,
            tuple(tuple(node.coordinates) for node in native.nodes),
            tuple(
                Element(element.label, tuple(element.connectivity), element.type)
                for element in native.elements
            ),
        )

    def field_names(self, step, frame):
        return tuple(self._fields(step, frame).keys())

    def _fields(self, step, frame):
        native = self._frame(step, frame)
        if self._field_repository_cache is None:
            self._field_repository_cache = native.fieldOutputs
        return self._field_repository_cache

    def _field(self, step, frame, name):
        fields = self._fields(step, frame)
        if name not in self._field_cache:
            self._field_cache[name] = fields[name]
        return self._field_cache[name]

    def _prepare_section_cache(self, key):
        # Retain native section metadata for only the current field query.
        if key != self._section_cache_key:
            self._section_cache.clear()
            self._section_cache_key = key

    def describe_field(self, step, frame, name, instances):
        field = self._field(step, frame, name)
        native_layout = _field_layout(field, self._constants)
        layout = native_layout._replace(position=str(native_layout.position))
        self._prepare_section_cache((step, frame, name))
        sections = {}
        max_point = 1
        for instance in instances:
            region = self._require_odb().rootAssembly.instances[instance]
            subset = field.getSubset(region=region).getSubset(
                position=native_layout.position
            )
            for block in subset.bulkDataBlocks:
                section = _section_point(block.sectionPoint)
                if section is not None:
                    # Preserve the current description-based grouping policy.
                    sections[section.description] = section
                    self._section_cache[section] = block.sectionPoint
                if block.integrationPoints is not None:
                    max_point = max(max_point, int(np.max(block.integrationPoints)))
        return FieldInfo(name, layout, tuple(sections.values()), max_point)

    def _native_section(self, field, key, section):
        self._prepare_section_cache(key)
        if section not in self._section_cache:
            for block in field.bulkDataBlocks:
                if _section_point(block.sectionPoint) == section:
                    self._section_cache[section] = block.sectionPoint
                    break
        if section not in self._section_cache:
            raise KeyError("Section point not found: {0}".format(section))
        return self._section_cache[section]

    def _native_position(self, position):
        return getattr(self._constants, str(position), position)

    def field_blocks(self, step, frame, name, instance, position, section=None):
        field = self._field(step, frame, name)
        if section is not None:
            native = self._native_section(field, (step, frame, name), section)
            field = field.getSubset(sectionPoint=native)
        return self._field_blocks(field, instance, position)

    def _field_blocks(self, field, instance, position):
        region = self._require_odb().rootAssembly.instances[instance]
        subset = field.getSubset(region=region).getSubset(
            position=self._native_position(position)
        )
        for block in subset.bulkDataBlocks:
            self._require_odb()
            for normalized in _normalize_bulk_blocks((block,), instance, position):
                yield normalized

    def orientation_blocks(self, step, frame, instances):
        """Yield owned quaternions using the legacy first-instance section policy."""
        if "S" not in self.field_names(step, frame):
            return
        field = self._field(step, frame, "S")
        instances = tuple(instances)
        section = None
        for instance in instances:
            region = self._require_odb().rootAssembly.instances[instance]
            subset = field.getSubset(region=region).getSubset(
                position=self._constants.CENTROID
            )
            for block in subset.bulkDataBlocks:
                section = block.sectionPoint
                break
            break
        for instance in instances:
            region = self._require_odb().rootAssembly.instances[instance]
            subset = field.getSubset(region=region).getSubset(
                position=self._constants.CENTROID
            )
            if section is not None:
                subset = subset.getSubset(sectionPoint=section)
            for block in subset.bulkDataBlocks:
                self._require_odb()
                if block.localCoordSystem is not None:
                    labels, values = _copy_rows(
                        block.elementLabels, block.localCoordSystem
                    )
                    if values.shape[1] > 4:
                        raise ValueError(
                            "Material orientation must have at most four components"
                        )
                    yield OrientationBlock(instance, labels, values)

    def history(self, step):
        for region_name, region in (
            self._require_odb().steps[step].historyRegions.items()
        ):
            for name, output in region.historyOutputs.items():
                self._require_odb()
                data = np.array(output.data, dtype=float, copy=True).reshape((-1, 2))
                yield HistorySeries(
                    step + "_" + region_name + "_" + name,
                    data[:, 0].copy(),
                    data[:, 1].copy(),
                )
