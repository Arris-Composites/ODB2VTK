"""Compare dictionary field placement with prepared vectorized label lookups.

Run with Abaqus Python, --baseline-python-dir PATH and --variant dictionary or
vector, followed by profile_exports.py arguments. The baseline path must contain
the complete saved odb2vtk_core package; each run selects exactly one package.
"""

import argparse
from pathlib import Path
import sys

from profile_exports import main as profile_main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-python-dir", required=True)
    parser.add_argument("--variant", choices=("dictionary", "vector"), required=True)
    args, profile_arguments = parser.parse_known_args()
    directory = (
        args.baseline_python_dir
        if args.variant == "dictionary"
        else str(Path(__file__).resolve().parents[1])
    )
    sys.path.insert(0, directory)
    import odb2vtk_core

    if (
        Path(odb2vtk_core.__file__).resolve().parent
        != Path(directory).resolve() / "odb2vtk_core"
    ):
        raise RuntimeError("A different odb2vtk_core package was already imported")
    sys.argv = [sys.argv[0]] + profile_arguments
    profile_main()


if __name__ == "__main__":
    main()
