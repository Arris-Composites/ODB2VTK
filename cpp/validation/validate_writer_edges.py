"""Read generated edge fixtures with VTK; requires NumPy and VTK."""

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import numpy as np
from vtkmodules.util.numpy_support import vtk_to_numpy

from compare_exports import read
from validate_writer_parity import binary_layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-exe", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    process = subprocess.run(
        [args.fixture_exe, str(output)], capture_output=True, text=True, timeout=60
    )
    assert process.returncode == 0 and not process.stderr, process.stderr
    name = 'values & "\n\t\rμ'
    original = np.array(
        [
            np.nan,
            np.inf,
            -np.inf,
            -0.0,
            1 + 2**-24,
            1 + 3 * 2**-24,
            np.finfo(np.float32).smallest_subnormal,
            np.finfo(np.float32).max,
        ]
    )
    expected = original.astype(np.float32)
    # Exercise the actual Python writer with the same plain records. This also
    # distinguishes native formatting defects from VTK's ASCII parser behavior.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
    from odb2vtk_core import writers

    points = np.zeros((8, 3))
    points[:, 0] = np.arange(8)
    points[0, 0] = 0.12345678901234567
    mesh = SimpleNamespace(
        points=points,
        connectivity=np.arange(8, dtype=np.int64),
        offsets=np.arange(1, 9, dtype=np.int64),
        cell_types=np.ones(8, dtype=np.int64),
    )
    field = SimpleNamespace(
        name=name,
        association="PointData",
        kind="Scalars",
        component_names=("component <μ>",),
        values=original.reshape(8, 1),
    )
    python_path = output / "special-python-ascii.vtu"
    with python_path.open("w", encoding="utf-8") as stream:
        writers.write_vtu(stream, mesh, [field], [])
    python_grid, python_messages = read(python_path)
    assert not python_messages
    python_values = vtk_to_numpy(python_grid.GetPointData().GetArray(name))
    negative_inf_reader_limitation = bool(np.isposinf(python_values[2]))
    results = []
    for encoding in ("ascii", "binary"):
        for kind in ("special", "empty"):
            path = output / (kind + "-" + encoding + ".vtu")
            grid, messages = read(path)
            assert not messages, (path, messages)
            rows = 8 if kind == "special" else 0
            assert grid.GetNumberOfPoints() == grid.GetNumberOfCells() == rows
            array = grid.GetPointData().GetArray(name)
            assert array is not None and array.GetComponentName(0) == "component <μ>"
            assert grid.GetPointData().GetScalars().GetName() == name
            values = vtk_to_numpy(array)
            assert values.dtype == np.dtype("float32") and values.shape == (rows,)
            differences = 0
            if rows:
                decoded_expected = expected.copy()
                if encoding == "ascii":
                    np.testing.assert_array_equal(values, python_values)
                    # VTK 9.7.1 consumes the minus sign before its fallback parser
                    # reads "inf". Both writers emit the correct signed token.
                    if negative_inf_reader_limitation:
                        decoded_expected[2] = np.inf
                    root = ET.parse(path)
                    raw_values = np.fromstring(
                        root.find(".//PointData/DataArray").text, sep=" "
                    )
                    np.testing.assert_array_equal(raw_values, original)
                assert np.array_equal(np.isnan(values), np.isnan(expected))
                assert np.array_equal(
                    np.isposinf(values), np.isposinf(decoded_expected)
                )
                assert np.array_equal(
                    np.isneginf(values), np.isneginf(decoded_expected)
                )
                assert np.signbit(values[3])
                finite = np.isfinite(expected)
                np.testing.assert_array_max_ulp(
                    values[finite],
                    expected[finite],
                    maxulp=1 if encoding == "ascii" else 0,
                )
                differences = int(np.sum(values[finite] != expected[finite]))
                coordinates = vtk_to_numpy(grid.GetPoints().GetData())
                assert coordinates.dtype == np.dtype("float64")
                assert coordinates[0, 0] == 0.12345678901234567
            record = dict(
                format=encoding,
                fixture=kind,
                reader_messages=messages,
                passed=True,
                differing_float32_values=differences,
            )
            if encoding == "binary":
                record["binary_layout"] = binary_layout(path)
            results.append(record)
    metadata = json.loads((output / "escaped.json").read_text(encoding="utf-8"))
    assert metadata["instances"] == [name]
    assert metadata["steps"] == [
        [name, [name + "-frame-" + str(i).zfill(2) for i in range(10)]]
    ]
    with (output / "escaped.csv").open(encoding="utf-8", newline="") as stream:
        assert list(csv.reader(stream)) == [[name], ["1.250000"]]
    entry = ET.parse(output / "escaped.pvd").find("Collection/DataSet")
    assert entry.attrib == dict(timestep="0.125", part="0", file=name + ".vtu")
    result = dict(
        passed=True,
        fixtures=results,
        unicode_and_control_escaping=True,
        json_schema=True,
        csv_quoting=True,
        pvd_schema=True,
        python_ascii_behavior_matches=True,
        ascii_negative_infinity_reader_limitation=negative_inf_reader_limitation,
    )
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
