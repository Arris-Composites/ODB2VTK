"""Dump Python's pre-Float32 values via its public ASCII export/source interfaces.

Run with Abaqus Python. The VTU text preserves the float64 assembly values before
a VTK reader converts the declared Float32 fields. No core methods are patched.
"""

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from odb2vtk_core import AbaqusSource, Converter, OutputOptions, Selection
from odb2vtk_core.history import assemble_history_table


def matrix(values):
    return dict(shape=list(values.shape), values=values.ravel().tolist())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odb", required=True)
    parser.add_argument("--instance", nargs="+", required=True)
    parser.add_argument("--frames", default="0,1")
    parser.add_argument("--step", default="Step-1")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    selection = Selection(
        args.instance, {args.step: tuple(map(int, args.frames.split(",")))}
    )
    options = OutputOptions.from_odb(args.odb, "_cpp_phase2_reference", write_pvd=False)
    with AbaqusSource.open(args.odb) as source:
        result = Converter(source).export_frames(selection, options)
        history = assemble_history_table(source.history(args.step))
    frames = []
    for exported in result.frames:
        piece = ET.parse(exported.path).find("UnstructuredGrid/Piece")
        points = np.fromstring(
            piece.find("Points/DataArray").text or "", sep=" "
        ).reshape(-1, 3)
        frame = dict(
            step=exported.step,
            frame=exported.frame,
            time=exported.timestep,
            points=matrix(points),
            fields=[],
        )
        for association in ("PointData", "CellData"):
            rows = int(
                piece.attrib[
                    "NumberOfPoints" if association == "PointData" else "NumberOfCells"
                ]
            )
            for field in piece.findall(association + "/DataArray"):
                width = int(field.attrib["NumberOfComponents"])
                values = np.fromstring(field.text or "", sep=" ").reshape(rows, width)
                labels = [
                    field.attrib["ComponentName" + str(i)]
                    for i in range(width)
                    if "ComponentName" + str(i) in field.attrib
                ]
                frame["fields"].append(
                    dict(
                        name=field.attrib["Name"],
                        association=association,
                        components=labels,
                        values=matrix(values),
                    )
                )
        for key, name in (
            ("connectivity", "connectivity"),
            ("offsets", "offsets"),
            ("cell_types", "types"),
        ):
            array = piece.find("Cells/DataArray[@Name='" + name + "']")
            frame[key] = np.fromstring(
                array.text or "", dtype=np.int64, sep=" "
            ).tolist()
        frames.append(frame)
    data = dict(
        frames=frames,
        history=dict(headers=list(history.headers), values=matrix(history.values)),
    )
    Path(args.report).write_text(json.dumps(data, indent=2) + "\n")
    print("Recorded Python numerical reference", args.report)


if __name__ == "__main__":
    main()
