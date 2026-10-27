"""Plain records shared by conversion and serialization modules.

Array storage belongs to the caller. These records do not retain Abaqus objects.
Named tuples keep the extracted code compatible with older Python runtimes.
"""

from collections import namedtuple
from numbers import Integral

from .errors import SelectionError

FieldLayout = namedtuple("FieldLayout", "kind component_names position")
FieldArray = namedtuple("FieldArray", "name association kind component_names values")
InstanceLabels = namedtuple("InstanceLabels", "name node_labels element_labels")
MeshIndex = namedtuple("MeshIndex", "node_map element_map node_count cell_count")
Element = namedtuple("Element", "label connectivity element_type")
InstanceMesh = namedtuple("InstanceMesh", "name coordinates elements")
MeshData = namedtuple("MeshData", "points connectivity offsets cell_types")
HistorySeries = namedtuple("HistorySeries", "name timestamps values")
HistoryTable = namedtuple("HistoryTable", "headers values")
CollectionEntry = namedtuple("CollectionEntry", "timestep part filename")
StepInfo = namedtuple("StepInfo", "name frame_count")
SectionPoint = namedtuple("SectionPoint", "number description")
FieldInfo = namedtuple("FieldInfo", "name layout section_points max_integration_point")
FieldBlock = namedtuple(
    "FieldBlock",
    "instance_name position labels values integration_points section_point",
)
OrientationBlock = namedtuple("OrientationBlock", "instance_name labels quaternions")
FrameExport = namedtuple("FrameExport", "step frame timestep path")
ExportResult = namedtuple("ExportResult", "paths frames diagnostics")
Diagnostic = namedtuple("Diagnostic", "step frame field message")
ProgressEvent = namedtuple("ProgressEvent", "kind path completed total")


class Selection(namedtuple("_Selection", "instances steps")):
    """An immutable snapshot of names and nonnegative frame indices.

    Steps accept a mapping or ordered (name, frames) pairs. Duplicate instances,
    steps, and frame indices are rejected. Empty instances/frame lists support
    history-only requests; frame export requires them to be nonempty.
    """

    __slots__ = ()

    def __new__(cls, instances, steps):
        if isinstance(instances, str):
            raise SelectionError("Instances must be a sequence of names")
        try:
            instances = tuple(instances)
            pairs = tuple(steps.items() if hasattr(steps, "items") else steps)
        except TypeError:
            raise SelectionError("Provide instance names and step/frame selections")
        if any(not isinstance(name, str) or not name for name in instances):
            raise SelectionError("Instance names must be nonempty strings")
        if len(set(instances)) != len(instances):
            raise SelectionError("Duplicate instance names are not allowed")
        normalized = []
        seen = set()
        for pair in pairs:
            try:
                name, frames = pair
            except (TypeError, ValueError):
                raise SelectionError("Each step must have a name and frame sequence")
            if not isinstance(name, str) or not name:
                raise SelectionError("Step names must be nonempty strings")
            if name in seen:
                raise SelectionError("Duplicate step: {0}".format(name))
            seen.add(name)
            if isinstance(frames, str):
                raise SelectionError("Frames must be integer sequences")
            try:
                frames = tuple(frames)
            except TypeError:
                raise SelectionError("Frames must be integer sequences")
            if any(
                isinstance(frame, bool) or not isinstance(frame, Integral) or frame < 0
                for frame in frames
            ):
                raise SelectionError("Frame indices must be nonnegative integers")
            frames = tuple(int(frame) for frame in frames)
            if len(set(frames)) != len(frames):
                raise SelectionError("Duplicate frame indices in step {0}".format(name))
            normalized.append((name, frames))
        if not normalized:
            raise SelectionError("Select at least one step")
        return super(Selection, cls).__new__(cls, instances, tuple(normalized))
