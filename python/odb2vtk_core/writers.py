"""Stream-based writers for the existing exporter formats.

Writers accept plain records and arrays and never query the source. Legacy XML
version strings, active-array attributes, numeric types, and CSV formatting are
preserved here; correcting these conventions is a separate behavior change.
"""

import json

import numpy as np


def _write_rows(stream, values):
    for row in values:
        stream.write(" ".join(str(value) for value in row) + "\n")


def write_data_array(stream, field):
    stream.write(
        '<DataArray type="Float32" Name="{0}" NumberOfComponents="{1}" '.format(
            field.name, field.values.shape[1]
        )
    )
    for index, label in enumerate(field.component_names):
        stream.write('ComponentName{0}="{1}" '.format(index, label))
    stream.write('format="ascii">\n')
    _write_rows(stream, field.values)
    stream.write("</DataArray>\n")


def _write_fields(stream, association, fields, metadata):
    stream.write("<{0} ".format(association))
    for kind in ("Tensors", "Vectors", "Scalars"):
        names = [field.name for field in metadata if field.kind == kind]
        if names:
            stream.write(
                '{0}="{1}" '.format(kind, ",".join("'{0}'".format(n) for n in names))
            )
    stream.write(">\n")
    for field in fields:
        write_data_array(stream, field)
        del field
    stream.write("</{0}>\n".format(association))


def write_vtu(
    stream, mesh, point_fields, cell_fields, point_metadata=None, cell_metadata=None
):
    """Write one frame; separate metadata permits lazy numerical field iterators.

    Existing callers may still supply field lists without separate metadata.
    Writers know only records and iterators, with no dependency on a data source.
    """
    if point_metadata is None:
        point_fields = list(point_fields)
        point_metadata = point_fields
    else:
        point_metadata = tuple(point_metadata)
    if cell_metadata is None:
        cell_fields = list(cell_fields)
        cell_metadata = cell_fields
    else:
        cell_metadata = tuple(cell_metadata)
    stream.write(
        '<VTKFile type="UnstructuredGrid" version="1,0" byte_order="LittleEndian">\n'
        "<UnstructuredGrid>\n"
        '<Piece NumberOfPoints="{0}" NumberOfCells="{1}">\n'.format(
            len(mesh.points), len(mesh.offsets)
        )
    )
    stream.write(
        '<Points>\n<DataArray type="Float64" NumberOfComponents="3" format="ascii">\n'
    )
    _write_rows(stream, mesh.points)
    stream.write("</DataArray>\n</Points>\n")
    _write_fields(stream, "PointData", point_fields, point_metadata)
    _write_fields(stream, "CellData", cell_fields, cell_metadata)
    stream.write("<Cells>\n")
    for name, values in (
        ("connectivity", mesh.connectivity),
        ("offsets", mesh.offsets),
        ("types", mesh.cell_types),
    ):
        stream.write(
            '<DataArray type="Int64" Name="{0}" format="ascii">\n'.format(name)
        )
        for value in values:
            stream.write("{0}\n".format(value))
        stream.write("</DataArray>\n")
    stream.write("</Cells>\n</Piece>\n</UnstructuredGrid>\n</VTKFile>")


def write_pvd(stream, entries):
    stream.write(
        '<VTKFile type="Collection" version="1.0" byte_order="LittleEndian" '
        'header_type="UInt64">\n<Collection>\n'
    )
    for entry in entries:
        stream.write(
            '<DataSet timestep="{0}" part="{1}" file="{2}"/>\n'.format(
                entry.timestep, entry.part, entry.filename
            )
        )
    stream.write("</Collection>\n</VTKFile>")


def write_csv(stream, table):
    np.savetxt(stream, np.array([table.headers]), "%s", ",")
    np.savetxt(stream, table.values, "%f", ",")


def write_header(stream, metadata):
    json.dump(metadata, stream, indent=4)
