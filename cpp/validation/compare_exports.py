"""Inventory C++/Python output differences using NumPy and optional VTK tooling.

Exit 0 means an inventory was written; --strict exits 1 when parity is false.
The Phase 1 executable is expected to expose differences, not pass parity.
"""

import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader


def read(path):
    reader = vtkXMLUnstructuredGridReader()
    messages = []
    reader.AddObserver("ErrorEvent", lambda *args: messages.append(args[1]))
    reader.AddObserver("WarningEvent", lambda *args: messages.append(args[1]))
    reader.SetFileName(str(path))
    reader.Update()
    if reader.GetErrorCode():
        raise ValueError("VTK reader error {0}".format(reader.GetErrorCode()))
    return reader.GetOutput(), messages


def compare(
    reference,
    candidates,
    reference_header=None,
    cpp_header=None,
    cpp_history=None,
    cpp_pvd=None,
):
    differences, rounding = [], []

    def note(kind, **details):
        differences.append(dict(kind=kind, **details))

    def values(a, b, name, frame):
        if a.shape != b.shape:
            note(
                "array_shape",
                frame=frame,
                array=name,
                python=list(a.shape),
                cpp=list(b.shape),
            )
            return
        if a.dtype != b.dtype:
            note(
                "array_type",
                frame=frame,
                array=name,
                python=str(a.dtype),
                cpp=str(b.dtype),
            )
        if np.array_equal(a, b, equal_nan=True):
            return
        mismatch = (a != b) & ~(np.isnan(a) & np.isnan(b))
        count = int(mismatch.sum())
        if a.dtype == b.dtype == np.dtype("float32"):
            try:
                np.testing.assert_array_max_ulp(a, b, maxulp=1)
                rounding.append(
                    dict(frame=frame, array=name, differing_values=count, max_ulps=1)
                )
                return
            except AssertionError:
                pass
        with np.errstate(invalid="ignore"):
            delta = np.abs(a.astype(float) - b.astype(float))
        finite = delta[np.isfinite(delta)]
        note(
            "array_values",
            frame=frame,
            array=name,
            differing_values=count,
            max_absolute_difference=float(finite.max()) if finite.size else None,
        )

    paths = [Path(p) for p in reference["paths"] if Path(p).suffix == ".vtu"]
    if len(paths) != len(candidates):
        note("frame_count", python=len(paths), cpp=len(candidates))
    checked = 0
    for ref, candidate in zip(paths, map(Path, candidates)):
        if ref.name != candidate.name:
            note("output_filename", python=ref.name, cpp=candidate.name)
        if not candidate.is_file():
            note("missing_vtu", file=candidate.name)
            continue
        try:
            left, ref_messages = read(ref)
            right, messages = read(candidate)
            if ref_messages:
                raise ValueError(
                    "Reference emitted VTK messages: " + repr(ref_messages)
                )
            if messages:
                note("reader_messages", frame=ref.name, messages=messages)
            checked += 1
            for accessor in ("GetNumberOfPoints", "GetNumberOfCells"):
                a, b = getattr(left, accessor)(), getattr(right, accessor)()
                if a != b:
                    note(
                        "mesh_count", frame=ref.name, property=accessor, python=a, cpp=b
                    )
            if left.GetPoints() is None or right.GetPoints() is None:
                note("missing_points", frame=ref.name)
                continue
            values(
                vtk_to_numpy(left.GetPoints().GetData()),
                vtk_to_numpy(right.GetPoints().GetData()),
                "coordinates",
                ref.name,
            )
            for accessor in ("GetConnectivityArray", "GetOffsetsArray"):
                values(
                    vtk_to_numpy(getattr(left.GetCells(), accessor)()),
                    vtk_to_numpy(getattr(right.GetCells(), accessor)()),
                    accessor,
                    ref.name,
                )
            if left.GetNumberOfCells() == right.GetNumberOfCells():
                if any(
                    left.GetCellType(i) != right.GetCellType(i)
                    for i in range(left.GetNumberOfCells())
                ):
                    note("cell_types", frame=ref.name)
            for association in ("GetPointData", "GetCellData"):
                a, b = getattr(left, association)(), getattr(right, association)()
                names = [
                    [v.GetArrayName(i) for i in range(v.GetNumberOfArrays())]
                    for v in (a, b)
                ]
                if names[0] != names[1]:
                    note(
                        "array_names_or_order",
                        frame=ref.name,
                        association=association,
                        python=names[0],
                        cpp=names[1],
                    )
                for name in names[0]:
                    x, y = a.GetArray(name), b.GetArray(name)
                    if y is None:
                        continue
                    values(
                        vtk_to_numpy(x),
                        vtk_to_numpy(y),
                        association + "/" + name,
                        ref.name,
                    )
                    labels = [
                        [
                            v.GetComponentName(i)
                            for i in range(v.GetNumberOfComponents())
                        ]
                        for v in (x, y)
                    ]
                    if labels[0] != labels[1]:
                        note(
                            "component_labels",
                            frame=ref.name,
                            array=name,
                            python=labels[0],
                            cpp=labels[1],
                        )
                for accessor in ("GetScalars", "GetVectors", "GetTensors"):
                    active = [getattr(v, accessor)() for v in (a, b)]
                    active = [None if v is None else v.GetName() for v in active]
                    if active[0] != active[1]:
                        note(
                            "active_array",
                            frame=ref.name,
                            association=association,
                            role=accessor,
                            python=active[0],
                            cpp=active[1],
                        )
        except Exception as error:
            note("reader_or_comparison_failure", frame=ref.name, error=str(error))

    if reference_header is not None:
        if cpp_header is None or not Path(cpp_header).is_file():
            note("missing_header")
        else:
            try:
                if json.loads(Path(reference_header).read_text()) != json.loads(
                    Path(cpp_header).read_text()
                ):
                    note("header_schema_or_values")
            except (ValueError, OSError) as error:
                note("header_schema_or_values", error=str(error))
    for suffix, candidate in ((".csv", cpp_history), (".pvd", cpp_pvd)):
        reference_path = next(
            (Path(v) for v in reference["paths"] if Path(v).suffix == suffix), None
        )
        if reference_path is None:
            continue
        if candidate is None or not Path(candidate).is_file():
            note("missing_history" if suffix == ".csv" else "missing_collection")
        else:
            try:
                if suffix == ".csv":
                    tables = []
                    for path in (reference_path, Path(candidate)):
                        with path.open(newline="") as stream:
                            tables.append(list(csv.reader(stream)))
                    if not tables[0] or not tables[1] or tables[0][0] != tables[1][0]:
                        note("history_schema_or_values")
                    else:
                        values(
                            np.asarray(tables[0][1:], dtype=float),
                            np.asarray(tables[1][1:], dtype=float),
                            "history",
                            "CSV",
                        )
                else:
                    roots = [
                        ET.parse(path).getroot() for path in (reference_path, candidate)
                    ]
                    entries = [
                        [
                            (
                                float(e.attrib["timestep"]),
                                int(e.attrib["part"]),
                                e.attrib["file"],
                            )
                            for e in root.findall("Collection/DataSet")
                        ]
                        for root in roots
                    ]
                    if (
                        roots[0].tag != roots[1].tag
                        or roots[0].attrib != roots[1].attrib
                        or entries[0] != entries[1]
                    ):
                        note("collection_schema_or_values")
                    for _, _, file in entries[1]:
                        if not (Path(candidate).parent / file).is_file():
                            note("collection_missing_frame", file=file)
            except (ValueError, OSError, KeyError, ET.ParseError) as error:
                note(
                    (
                        "history_schema_or_values"
                        if suffix == ".csv"
                        else "collection_schema_or_values"
                    ),
                    error=str(error),
                )
    return dict(
        parity=not differences,
        frames_checked=checked,
        differences=differences,
        float32_rounding=rounding,
        float32_ulp_limit=1,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-report", required=True)
    parser.add_argument("--cpp-vtu", nargs="+", required=True)
    parser.add_argument("--reference-header")
    parser.add_argument("--cpp-header")
    parser.add_argument("--cpp-history")
    parser.add_argument("--cpp-pvd")
    parser.add_argument("--report", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = compare(
        json.loads(Path(args.python_report).read_text()),
        args.cpp_vtu,
        args.reference_header,
        args.cpp_header,
        args.cpp_history,
        args.cpp_pvd,
    )
    Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
    print(
        "Parity: {0}; checked {1} frames; {2} differences".format(
            result["parity"], result["frames_checked"], len(result["differences"])
        )
    )
    return 1 if args.strict and not result["parity"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
