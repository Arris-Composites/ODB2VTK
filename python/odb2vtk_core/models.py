"""Plain records shared by conversion and serialization modules.

Array storage belongs to the caller. These records do not retain Abaqus objects.
Named tuples keep the extracted code compatible with older Python runtimes.
"""

from collections import namedtuple

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
