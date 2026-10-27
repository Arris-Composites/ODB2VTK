"""Uncompressed appended-raw VTU, streaming arrays without VTK dependencies.

XML offsets refer to UInt64 byte-count headers after the appended underscore.
All payloads are C-order little endian, converted in bounded row chunks.
"""

import struct

import numpy as np

from .writers import _active_attributes, _attribute, _component_count

_CHUNK_BYTES = 1024 * 1024
_HEADER_BYTES = 8
_FLOAT32 = np.dtype("<f4")
_FLOAT64 = np.dtype("<f8")
_INT64 = np.dtype("<i8")


def _write_array(stream, values, shape, dtype):
    values = np.asarray(values)
    if values.shape != shape:
        raise ValueError(
            "Array shape differs from binary metadata: {0} != {1}".format(
                values.shape, shape
            )
        )
    width = shape[1] if len(shape) == 2 else 1
    size = shape[0] * width * dtype.itemsize
    stream.write(struct.pack("<Q", size))
    chunk_rows = max(1, _CHUNK_BYTES // (width * dtype.itemsize))
    for start in range(0, shape[0], chunk_rows):
        block = np.ascontiguousarray(values[start : start + chunk_rows], dtype=dtype)
        stream.write(memoryview(block).cast("B"))


def _write_fields(stream, fields, metadata, rows, association):
    fields = iter(fields)
    sentinel = object()
    for expected in metadata:
        field = next(fields, sentinel)
        if field is sentinel:
            raise ValueError("Missing binary field: " + expected.name)
        if (
            field.name != expected.name
            or field.association != association
            or field.kind != expected.kind
            or tuple(field.component_names) != tuple(expected.component_names)
        ):
            raise ValueError("Binary field metadata changed: " + expected.name)
        _write_array(stream, field.values, (rows, _component_count(expected)), _FLOAT32)
        # Release the current numerical field before advancing its generator.
        del field
    if next(fields, sentinel) is not sentinel:
        raise ValueError("More binary fields than declared metadata")


def write_vtu(
    stream, mesh, point_fields, cell_fields, point_metadata=None, cell_metadata=None
):
    """Write to a binary stream, borrowing immutable mesh/layout metadata.

    Metadata lets numerical field iterators remain lazy. Without it, direct
    callers may supply field lists, just as with the ASCII writer. Fields must
    match metadata in order, identity, components and tuple count. Chunk storage
    is at most _CHUNK_BYTES or one row, whichever is larger.
    """
    if point_metadata is None:
        point_fields = list(point_fields)
        point_metadata = point_fields
    if cell_metadata is None:
        cell_fields = list(cell_fields)
        cell_metadata = cell_fields
    point_metadata, cell_metadata = tuple(point_metadata), tuple(cell_metadata)
    points, cells = len(mesh.points), len(mesh.offsets)
    offset = 0

    def text(value):
        stream.write(value.encode("utf-8"))

    def array(vtk_type, shape, dtype, name=None, component_names=()):
        nonlocal offset
        width = shape[1] if len(shape) == 2 else 1
        if width < 1:
            raise ValueError("Binary arrays must have at least one component")
        text('<DataArray type="{0}" '.format(vtk_type))
        if name is not None:
            text('Name="{0}" '.format(_attribute(name)))
        if len(shape) == 2:
            text('NumberOfComponents="{0}" '.format(width))
        for index, label in enumerate(component_names):
            text('ComponentName{0}="{1}" '.format(index, _attribute(label)))
        text('format="appended" offset="{0}"/>\n'.format(offset))
        offset += _HEADER_BYTES + shape[0] * width * dtype.itemsize

    text(
        '<VTKFile type="UnstructuredGrid" version="1.0" '
        'byte_order="LittleEndian" header_type="UInt64">\n<UnstructuredGrid>\n'
        '<Piece NumberOfPoints="{0}" NumberOfCells="{1}">\n'.format(points, cells)
    )
    text("<Points>\n")
    array("Float64", (points, 3), _FLOAT64)
    text("</Points>\n")
    for association, metadata, rows in (
        ("PointData", point_metadata, points),
        ("CellData", cell_metadata, cells),
    ):
        text("<{0} ".format(association))
        for attribute in _active_attributes(metadata):
            text(attribute)
        text(">\n")
        for field in metadata:
            array(
                "Float32",
                (rows, _component_count(field)),
                _FLOAT32,
                field.name,
                field.component_names,
            )
        text("</{0}>\n".format(association))
    topology = (mesh.connectivity, mesh.offsets, mesh.cell_types)
    text("<Cells>\n")
    for name, values in zip(("connectivity", "offsets", "types"), topology):
        array("Int64", (len(values),), _INT64, name)
    text('</Cells>\n</Piece>\n</UnstructuredGrid>\n<AppendedData encoding="raw">\n_')
    _write_array(stream, mesh.points, (points, 3), _FLOAT64)
    _write_fields(stream, point_fields, point_metadata, points, "PointData")
    _write_fields(stream, cell_fields, cell_metadata, cells, "CellData")
    for values in topology:
        _write_array(stream, values, (len(values),), _INT64)
    text("\n</AppendedData>\n</VTKFile>")
