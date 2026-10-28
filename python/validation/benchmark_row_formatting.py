"""Compare scalar/three-component formatting with a saved chunked writer.

Run with Abaqus Python. Pass a --baseline-writer path and --variant, followed by
normal profile_exports.py arguments. Only row formatting is replaced; chunking,
the converter/source, and all other serialization stay at their current versions.
"""

import argparse
import importlib.util
from pathlib import Path
import sys

from profile_exports import main as profile_main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-writer", required=True)
    parser.add_argument(
        "--variant", choices=("baseline", "scalar", "three", "both"), required=True
    )
    args, profile_arguments = parser.parse_known_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from odb2vtk_core import writers

    spec = importlib.util.spec_from_file_location(
        "baseline_writers", args.baseline_writer
    )
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    specialized = writers._write_rows
    if args.variant == "baseline":
        writers._write_rows = baseline._write_rows
    elif args.variant != "both":
        width = 1 if args.variant == "scalar" else 3

        def selected(stream, values):
            function = specialized if values.shape[1] == width else baseline._write_rows
            function(stream, values)

        writers._write_rows = selected
    sys.argv = [sys.argv[0]] + profile_arguments
    profile_main()


if __name__ == "__main__":
    main()
