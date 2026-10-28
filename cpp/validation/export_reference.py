"""Export public Python reference files; run with Abaqus Python."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from odb2vtk_core import AbaqusSource, Converter, OutputOptions, Selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odb", required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--instance", nargs="+", required=True)
    parser.add_argument("--frames", default="0,1")
    parser.add_argument("--format", choices=("ascii", "binary"), required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    defaults = OutputOptions.from_odb(args.odb)
    outputs = OutputOptions(args.directory, defaults.name, vtu_format=args.format)
    selection = Selection(
        args.instance, {"Step-1": tuple(map(int, args.frames.split(",")))}
    )
    with AbaqusSource.open(args.odb) as source:
        converter = Converter(source)
        header = converter.export_header(outputs)
        history = converter.export_history(selection, outputs)
        frames = converter.export_frames(selection, outputs)
        converter.export_collection(selection, outputs)
    Path(args.report).write_text(
        json.dumps(
            dict(paths=list(history.paths + frames.paths), header=header.paths[0]),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
