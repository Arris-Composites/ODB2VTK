"""Compare a saved uncached source with current frame/field handle caching.

Run with Abaqus Python, --baseline-source PATH and --variant uncached or cached,
followed by normal profile_exports.py arguments. Only the source implementation
changes; converter and writers stay at their current versions.
"""

import argparse
import importlib.util
from pathlib import Path
import sys

from profile_exports import main as profile_main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-source", required=True)
    parser.add_argument("--variant", choices=("uncached", "cached"), required=True)
    args, profile_arguments = parser.parse_known_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import odb2vtk_core

    spec = importlib.util.spec_from_file_location(
        "odb2vtk_core._baseline_source", args.baseline_source
    )
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if args.variant == "uncached":
        odb2vtk_core.AbaqusSource = baseline.AbaqusSource
    sys.argv = [sys.argv[0]] + profile_arguments
    profile_main()


if __name__ == "__main__":
    main()
