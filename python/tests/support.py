"""In-memory source and native-handle stand-ins for source contract tests."""

from collections import OrderedDict
import types

import numpy as np

from odb2vtk_core.models import (
    Element,
    FieldBlock,
    FieldInfo,
    FieldLayout,
    HistorySeries,
    InstanceMesh,
    OrientationBlock,
    SectionPoint,
    StepInfo,
)


def copy_block(block):
    return block._replace(
        labels=block.labels.copy(),
        values=block.values.copy(),
        integration_points=(
            None
            if block.integration_points is None
            else block.integration_points.copy()
        ),
    )


class InMemorySource:
    """Satisfy the normalized source interface without simulating Abaqus queries."""

    def __init__(self, meshes, layouts, blocks, times, histories, orientations):
        self._meshes = OrderedDict((mesh.name, mesh) for mesh in meshes)
        self._layouts = layouts
        self._blocks = blocks
        self._times = times
        self._histories = histories
        self._orientations = orientations
        self._closed = False
        self.close_calls = 0

    @property
    def closed(self):
        return self._closed

    def _check_open(self):
        if self.closed:
            raise RuntimeError("ODB source is closed")

    def close(self):
        if not self.closed:
            self.close_calls += 1
            self._closed = True

    def __enter__(self):
        self._check_open()
        return self

    def __exit__(self, *args):
        self.close()
        return False

    @property
    def instance_names(self):
        self._check_open()
        return tuple(self._meshes)

    @property
    def steps(self):
        self._check_open()
        return tuple(StepInfo(name, len(times)) for name, times in self._times.items())

    def frame_time(self, step, frame):
        self._check_open()
        return self._times[step][frame]

    def mesh(self, instance):
        self._check_open()
        mesh = self._meshes[instance]
        return mesh._replace(
            coordinates=np.array(mesh.coordinates, dtype=float, copy=True)
        )

    def field_names(self, step, frame):
        self._check_open()
        return tuple(self._layouts[(step, frame)])

    def describe_field(self, step, frame, name, instances):
        self._check_open()
        layout = self._layouts[(step, frame)][name]
        sections = OrderedDict()
        maximum = 1
        for block in self._blocks[(step, frame, name)]:
            if (
                block.instance_name not in instances
                or block.position != layout.position
            ):
                continue
            if block.section_point is not None:
                sections[block.section_point.description] = block.section_point
            if block.integration_points is not None:
                maximum = max(maximum, int(block.integration_points.max()))
        return FieldInfo(name, layout, tuple(sections.values()), maximum)

    def field_blocks(self, step, frame, name, instance, position, section=None):
        self._check_open()
        for block in self._blocks[(step, frame, name)]:
            self._check_open()
            if block.instance_name != instance or block.position != position:
                continue
            if section is not None and block.section_point != section:
                continue
            yield copy_block(block)

    def orientation_blocks(self, step, frame, instances):
        self._check_open()
        for block in self._orientations[(step, frame)]:
            self._check_open()
            if block.instance_name in instances:
                yield block._replace(
                    labels=block.labels.copy(), quaternions=block.quaternions.copy()
                )

    def history(self, step):
        self._check_open()
        for series in self._histories[step]:
            self._check_open()
            yield series._replace(
                timestamps=series.timestamps.copy(), values=series.values.copy()
            )


def make_source(include_stress=True):
    meshes = []
    nodal = []
    scalars = []
    stress = []
    orientations = []
    sections = (SectionPoint(1, "Top"), SectionPoint(2, "Bottom"))
    for name, offset in (("A", 0), ("B", 100)):
        meshes.append(
            InstanceMesh(
                name,
                (3, 1, 4, 2),
                tuple((label, offset, 0) for label in (3, 1, 4, 2)),
                (Element(7, (1, 2, 3, 4), "S4"),),
            )
        )
        nodal.append(
            FieldBlock(
                name,
                "NODAL",
                np.array([1, 2, 3, 4]),
                np.array([[offset + label, 0, 0] for label in (1, 2, 3, 4)]),
                None,
                None,
            )
        )
        scalars.append(
            FieldBlock(
                name,
                "NODAL",
                np.array([1, 2, 3, 4]),
                np.array([[offset + label] for label in (1, 2, 3, 4)]),
                None,
                None,
            )
        )
        orientations.append(
            OrientationBlock(name, np.array([7]), np.array([[0.0, 0.0, 0.0, 1.0]]))
        )
        for index, section in enumerate(sections):
            base = offset + index * 10
            stress.append(
                FieldBlock(
                    name,
                    "INTEGRATION_POINT",
                    np.array([7, 7]),
                    np.array([[base + 1, base + 2], [base + 3, base + 4]]),
                    np.array([1, 2]),
                    section,
                )
            )
            stress.append(
                FieldBlock(
                    name,
                    "CENTROID",
                    np.array([7]),
                    np.array([[base + 90, base + 91]]),
                    None,
                    section,
                )
            )
    layouts = OrderedDict(
        [
            ("U", FieldLayout("Vectors", ("U1", "U2", "U3"), "NODAL")),
            ("TEMP", FieldLayout("Scalars", ("0",), "NODAL")),
        ]
    )
    blocks = {("Step-1", 0, "U"): nodal, ("Step-1", 0, "TEMP"): scalars}
    if include_stress:
        layouts["S"] = FieldLayout("Tensors", ("S11", "S22"), "INTEGRATION_POINT")
        blocks[("Step-1", 0, "S")] = stress
    histories = [
        HistorySeries(
            "Step-1_" + name + "_U",
            np.array([0.0, 1.0]),
            np.array([value, value + 1.0]),
        )
        for name, value in (("A", 11), ("B", 21))
    ]
    return InMemorySource(
        meshes,
        {("Step-1", 0): layouts},
        blocks,
        OrderedDict([("Step-1", (0.5,))]),
        {"Step-1": histories},
        {("Step-1", 0): orientations if include_stress else []},
    )


class NativeField:
    """Third-party handle stand-in; only source-adapter tests use this type."""

    def __init__(self, kind, components, position, blocks, filters=None):
        self.type = kind
        self.componentLabels = components
        self.locations = [types.SimpleNamespace(position=position)]
        self.blocks = blocks
        self.filters = filters or {}

    def getSubset(self, **filters):
        return NativeField(
            self.type,
            self.componentLabels,
            self.locations[0].position,
            self.blocks,
            dict(self.filters, **filters),
        )

    @property
    def bulkDataBlocks(self):
        return [
            block
            for instance, position, block in self.blocks
            if ("region" not in self.filters or instance == self.filters["region"].name)
            and ("position" not in self.filters or position == self.filters["position"])
            and (
                "sectionPoint" not in self.filters
                or block.sectionPoint == self.filters["sectionPoint"]
            )
        ]


class NativeOdb:
    def __init__(self, fixture, invalidate_on_close=False):
        self.close_calls = 0
        self.invalidate_on_close = invalidate_on_close
        self.arrays = []
        self.rootAssembly = types.SimpleNamespace(instances=OrderedDict())
        for instance in fixture.instance_names:
            mesh = fixture.mesh(instance)
            self.rootAssembly.instances[instance] = types.SimpleNamespace(
                name=instance,
                nodes=[
                    types.SimpleNamespace(label=label, coordinates=coordinates)
                    for label, coordinates in zip(mesh.node_labels, mesh.coordinates)
                ],
                elements=[
                    types.SimpleNamespace(
                        label=e.label, connectivity=e.connectivity, type=e.element_type
                    )
                    for e in mesh.elements
                ],
            )
        fields = OrderedDict()
        sections = {}
        for name in fixture.field_names("Step-1", 0):
            info = fixture.describe_field("Step-1", 0, name, fixture.instance_names)
            blocks = []
            for block in fixture._blocks[("Step-1", 0, name)]:
                section = sections.setdefault(block.section_point, None)
                if block.section_point is not None and section is None:
                    section = types.SimpleNamespace(
                        number=block.section_point.number,
                        description=block.section_point.description,
                    )
                    sections[block.section_point] = section
                coordinates = (
                    np.array([[0.0, 0.0, 0.0, 1.0]])
                    if name == "S" and block.position == "CENTROID"
                    else None
                )
                native = types.SimpleNamespace(
                    nodeLabels=block.labels if block.position == "NODAL" else None,
                    elementLabels=block.labels if block.position != "NODAL" else None,
                    data=block.values,
                    integrationPoints=block.integration_points,
                    sectionPoint=section,
                    localCoordSystem=coordinates,
                )
                self.arrays.extend(
                    [
                        native.data,
                        native.nodeLabels,
                        native.elementLabels,
                        native.integrationPoints,
                        coordinates,
                    ]
                )
                blocks.append((block.instance_name, block.position, native))
            native_kind = {
                "Scalars": "SCALAR",
                "Vectors": "VECTOR",
                "Tensors": "TENSOR",
            }[info.layout.kind]
            components = () if native_kind == "SCALAR" else info.layout.component_names
            fields[name] = NativeField(
                native_kind, components, info.layout.position, blocks
            )
        regions = OrderedDict()
        for series in fixture.history("Step-1"):
            region = series.name.split("_")[1]
            regions[region] = types.SimpleNamespace(
                historyOutputs={
                    "U": types.SimpleNamespace(
                        data=list(zip(series.timestamps, series.values))
                    )
                }
            )
        self.steps = OrderedDict(
            [
                (
                    "Step-1",
                    types.SimpleNamespace(
                        frames=[
                            types.SimpleNamespace(frameValue=0.5, fieldOutputs=fields)
                        ],
                        historyRegions=regions,
                    ),
                )
            ]
        )

    def close(self):
        self.close_calls += 1
        if self.invalidate_on_close:
            for array in self.arrays:
                if array is not None:
                    array.fill(-999)


CONSTANTS = types.SimpleNamespace(
    NODAL="NODAL",
    INTEGRATION_POINT="INTEGRATION_POINT",
    CENTROID="CENTROID",
    SCALAR="SCALAR",
    VECTOR="VECTOR",
)
