"""Compare ASCII/binary profile reports using VTK; measure warm reader times.

Run in an ordinary Python environment with NumPy and VTK, not Abaqus Python.
Report paths must still exist. This validates decoded output, not byte identity.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import time
import xml.etree.ElementTree as ET

import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridReader


def read(path):
    messages = []
    started = time.perf_counter()
    reader = vtkXMLUnstructuredGridReader()
    reader.AddObserver("ErrorEvent", lambda *args: messages.append(args[1]))
    reader.AddObserver("WarningEvent", lambda *args: messages.append(args[1]))
    reader.SetFileName(str(path))
    reader.Update()
    result = reader.GetOutput()
    elapsed = time.perf_counter() - started
    assert not messages and reader.GetErrorCode() == 0, (path, messages)
    return result, elapsed


def compare_grid(a, b):
    rounding = []
    assert a.GetNumberOfPoints() == b.GetNumberOfPoints()
    assert a.GetNumberOfCells() == b.GetNumberOfCells()
    assert (
        a.GetPoints().GetData().GetDataType() == b.GetPoints().GetData().GetDataType()
    )
    np.testing.assert_array_equal(
        vtk_to_numpy(a.GetPoints().GetData()), vtk_to_numpy(b.GetPoints().GetData())
    )
    for accessor in ("GetConnectivityArray", "GetOffsetsArray"):
        np.testing.assert_array_equal(
            vtk_to_numpy(getattr(a.GetCells(), accessor)()),
            vtk_to_numpy(getattr(b.GetCells(), accessor)()),
        )
    assert all(
        a.GetCellType(i) == b.GetCellType(i) for i in range(a.GetNumberOfCells())
    )
    for association in ("GetPointData", "GetCellData"):
        left, right = getattr(a, association)(), getattr(b, association)()
        assert left.GetNumberOfArrays() == right.GetNumberOfArrays()
        for i in range(left.GetNumberOfArrays()):
            x, y = left.GetArray(i), right.GetArray(i)
            assert x.GetName() == y.GetName()
            assert x.GetDataType() == y.GetDataType()
            assert x.GetNumberOfComponents() == y.GetNumberOfComponents()
            old, new = vtk_to_numpy(x), vtk_to_numpy(y)
            if old.dtype == np.dtype("float32") and old.size:
                np.testing.assert_array_max_ulp(old, new, maxulp=1)
                different = (old != new) & ~(np.isnan(old) & np.isnan(new))
                if np.any(different):
                    rounding.append(
                        dict(
                            association=association,
                            field=x.GetName(),
                            count=int(different.sum()),
                            max_ulps=1,
                            max_absolute_difference=float(
                                np.abs(
                                    old[different].astype(float)
                                    - new[different].astype(float)
                                ).max()
                            ),
                        )
                    )
            else:
                np.testing.assert_array_equal(old, new)
            for j in range(x.GetNumberOfComponents()):
                assert x.GetComponentName(j) == y.GetComponentName(j)
        for active in ("GetScalars", "GetVectors", "GetTensors"):
            x, y = getattr(left, active)(), getattr(right, active)()
            assert (None if x is None else x.GetName()) == (
                None if y is None else y.GetName()
            )
    return rounding


def compare(reference, candidate, repeats=5):
    assert repeats > 0
    left, right = reference["paths"], candidate["paths"]
    assert len(left) == len(right)
    pairs = []
    rounding = []
    for a, b in zip(map(Path, left), map(Path, right)):
        assert a.suffix == b.suffix
        if a.suffix == ".vtu":
            assert a.name == b.name
            for difference in compare_grid(read(a)[0], read(b)[0]):
                rounding.append(dict(frame=a.name, **difference))
            pairs.append((a, b))
        else:
            assert (
                hashlib.sha256(a.read_bytes()).digest()
                == hashlib.sha256(b.read_bytes()).digest()
            )
            if a.suffix == ".pvd":
                entries = ET.parse(a).findall("Collection/DataSet")
                assert [e.attrib["file"] for e in entries] == [
                    p.name for p in map(Path, left) if p.suffix == ".vtu"
                ]
                for e in entries:
                    assert (a.parent / e.attrib["file"]).is_file()
                    assert (b.parent / e.attrib["file"]).is_file()
    times = {"reference": [], "candidate": []}
    for repeat in range(repeats):
        totals = dict(reference=0.0, candidate=0.0)
        for a, b in pairs:
            order = (("reference", a), ("candidate", b))
            if repeat % 2:
                order = order[::-1]
            for name, path in order:
                grid, elapsed = read(path)
                totals[name] += elapsed
                del grid
        for name in totals:
            times[name].append(totals[name])
    return dict(
        passed=True,
        vtu_pairs=len(pairs),
        max_float32_ulps_allowed=1,
        float32_rounding_differences=rounding,
        reference_vtu_bytes=sum(a.stat().st_size for a, _ in pairs),
        candidate_vtu_bytes=sum(b.stat().st_size for _, b in pairs),
        read_seconds=times,
        median_read_seconds={k: statistics.median(v) for k, v in times.items()},
        method="One untimed reader validation per file, then five alternating warm reads per file; totals per export selection. Fresh VTK reader objects, existing OS caches; imports excluded. All numerical values, types, topology, labels, active arrays and PVD references compared.",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-report", required=True)
    parser.add_argument("--candidate-report", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    result = compare(
        json.loads(Path(args.reference_report).read_text()),
        json.loads(Path(args.candidate_report).read_text()),
    )
    Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
