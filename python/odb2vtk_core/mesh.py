"""Translate plain mesh data and labels into VTK topology."""

import numpy as np

from .models import MeshData, MeshIndex

# Preserve the converter's existing element-family matching and precedence.
_CELL_TYPES = (
    ("C3D4", 10),
    ("C3D6", 13),
    ("C3D8", 12),
    ("C3D10", 24),
    ("C3D15", 26),
    ("C3D20", 25),
    ("S3", 5),
    ("S4", 9),
    ("S8", 23),
    ("S9", 28),
    ("B31", 3),
    ("R3D3", 5),
    ("R3D4", 9),
    ("CAX3", 5),
    ("RNODE3D", 1),
    ("M3D6", 22),
)


def vtk_cell_type(element_type):
    for family, cell_type in _CELL_TYPES:
        if family in element_type:
            return cell_type
    raise ValueError("{0} element type not found".format(element_type))


def build_label_maps(instances):
    """Assign global indices in selected instance and source label order."""
    node_map = {}
    element_map = {}
    node_count = 0
    cell_count = 0
    for instance in instances:
        nodes = {}
        elements = {}
        for label in instance.node_labels:
            nodes[label] = node_count
            node_count += 1
        for element in instance.elements:
            elements[element.label] = cell_count
            cell_count += 1
        node_map[instance.name] = nodes
        element_map[instance.name] = elements
    return MeshIndex(node_map, element_map, node_count, cell_count)


def build_mesh(instances, node_map):
    """Flatten coordinates and instance-local connectivity without source I/O."""
    points = []
    connectivity = []
    offsets = []
    cell_types = []
    for instance in instances:
        coordinates = np.asarray(instance.coordinates, dtype=float)
        if not coordinates.size:
            coordinates = coordinates.reshape((0, 3))
        if coordinates.shape != (len(instance.node_labels), 3):
            raise ValueError("Mesh coordinates must have three components per node")
        points.append(coordinates)
        for element in instance.elements:
            connectivity.extend(
                node_map[instance.name][label] for label in element.connectivity
            )
            offsets.append(len(connectivity))
            cell_types.append(vtk_cell_type(element.element_type))
    return MeshData(
        np.concatenate(points, axis=0) if points else np.empty((0, 3), dtype=float),
        np.asarray(connectivity, dtype=np.int64),
        np.asarray(offsets, dtype=np.int64),
        np.asarray(cell_types, dtype=np.int64),
    )
