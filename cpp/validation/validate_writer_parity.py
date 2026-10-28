"""Compare native writer files with Python in both formats; requires VTK/NumPy.

Set PATH to the Abaqus runtime DLL directory before launching. The native probe
uses the maintained Exporter directly, independently of the Phase 4 CLI parser.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET

from compare_exports import compare


def binary_layout(path):
    data = path.read_bytes()
    marker = b'<AppendedData encoding="raw">\n_'
    start = data.index(marker) + len(marker)
    prefix = data[: start - len(marker)]
    root = ET.fromstring(prefix + b"</VTKFile>")
    arrays = root.findall(".//DataArray")
    assert root.attrib["header_type"] == "UInt64"
    assert root.attrib["byte_order"] == "LittleEndian"
    assert "compressor" not in root.attrib
    piece = root.find("UnstructuredGrid/Piece")
    points, cells = int(piece.attrib["NumberOfPoints"]), int(
        piece.attrib["NumberOfCells"]
    )
    counts = {}
    for association, rows in (
        ("Points", points),
        ("PointData", points),
        ("CellData", cells),
    ):
        for array in piece.findall(association + "/DataArray"):
            counts[id(array)] = rows * int(array.attrib.get("NumberOfComponents", 1))
    offset = 0
    sizes = {"Float64": 8, "Float32": 4, "Int64": 8}
    for array in arrays:
        assert array.attrib["format"] == "appended"
        assert int(array.attrib["offset"]) == offset
        size = struct.unpack_from("<Q", data, start + offset)[0]
        assert size % sizes[array.attrib["type"]] == 0
        if id(array) in counts:
            assert size == counts[id(array)] * sizes[array.attrib["type"]]
        if array.attrib.get("Name") in ("offsets", "types"):
            assert size == cells * 8
        offset += 8 + size
    assert data[start + offset :] == b"\n</AppendedData>\n</VTKFile>"
    return dict(arrays=len(arrays), payload_bytes=offset, exact_layout=True)


def run(command, report=None):
    if report is not None:
        report.unlink(missing_ok=True)
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode or result.stderr or "Traceback" in result.stdout:
        raise RuntimeError((command, result.returncode, result.stdout, result.stderr))
    if report is not None and not report.is_file():
        raise RuntimeError("Reference report was not produced: " + result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True)
    parser.add_argument("--odb", required=True)
    parser.add_argument("--instance", nargs="+", required=True)
    parser.add_argument("--frames", default="0,1")
    parser.add_argument("--output", required=True)
    parser.add_argument("--abaqus", default=shutil.which("abaqus"))
    args = parser.parse_args()
    if not args.abaqus:
        parser.error("Abaqus launcher not found")
    odb = Path(args.odb).resolve()
    before = hashlib.sha256(odb.read_bytes()).hexdigest()
    output = Path(args.output).resolve()
    name = odb.name.split(".")[0]
    records = []
    for encoding in ("ascii", "binary"):
        directory = output / encoding
        directory.mkdir(parents=True, exist_ok=True)
        reference_report = directory / "python-report.json"
        run(
            [
                args.abaqus,
                "python",
                str(Path(__file__).with_name("export_reference.py")),
                "--odb",
                str(odb),
                "--directory",
                str(directory / "python"),
                "--format",
                encoding,
                "--frames",
                args.frames,
                "--report",
                str(reference_report),
                "--instance",
                *args.instance,
            ],
            reference_report,
        )
        run(
            [
                args.probe,
                str(odb),
                str(directory / "cpp"),
                encoding,
                ",".join(args.instance),
                args.frames,
            ]
        )
        reference = json.loads(reference_report.read_text())
        data_directory = directory / "cpp" / name
        candidates = [
            data_directory / Path(path).name
            for path in reference["paths"]
            if path.endswith(".vtu")
        ]
        result = compare(
            reference,
            candidates,
            reference["header"],
            directory / "cpp" / (name + ".json"),
            data_directory / (name + ".csv"),
            data_directory / (name + ".pvd"),
        )
        assert result["parity"], result
        assert hashlib.sha256(odb.read_bytes()).hexdigest() == before
        result.update(format=encoding, input_unchanged=True)
        if encoding == "binary":
            result["binary_layout"] = [binary_layout(path) for path in candidates]
        (directory / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
        records.append(result)
        print(encoding + ": " + json.dumps(result), flush=True)
    assert not list(output.rglob(".odb2vtk-*.tmp"))
    (output / "results.json").write_text(
        json.dumps(dict(odb_sha256=before, formats=records), indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
