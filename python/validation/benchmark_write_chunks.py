"""Experiment wrapper for profile_exports.py; run with Abaqus Python.

Pass --chunk-rows N or --baseline-writer PATH, then normal profiling arguments.
The baseline is a saved writers.py from before batching, not an old converter.
Only this process is configured; production exposes no chunk-size option.
"""

import argparse
import importlib.util
from pathlib import Path
import sys

from profile_exports import main as profile_main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    variant = parser.add_mutually_exclusive_group(required=True)
    variant.add_argument("--chunk-rows", type=int, choices=(256, 1024, 4096))
    variant.add_argument("--baseline-writer")
    args, profile_arguments = parser.parse_known_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from odb2vtk_core import writers

    if args.baseline_writer:
        spec = importlib.util.spec_from_file_location(
            "baseline_writers", args.baseline_writer
        )
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        # Keep the same converter/source and all non-VTU operations. The saved
        # function resolves its own original helper functions in that module.
        writers.write_vtu = baseline.write_vtu
    else:
        writers._WRITE_CHUNK_ROWS = args.chunk_rows
    sys.argv = [sys.argv[0]] + profile_arguments
    profile_main()


if __name__ == "__main__":
    main()
