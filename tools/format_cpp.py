"""Format tracked C++ files with the clang-format 14 version used locally."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLANG_FORMAT_VERSION = "14.0.6"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="check without modifying files"
    )
    args = parser.parse_args()
    git, uvx = shutil.which("git"), shutil.which("uvx")
    if not git or not uvx:
        parser.error("Git and uv (including uvx) must be available on PATH")
    result = subprocess.run(
        [git, "ls-files", "-z", "--", "cpp/*.cpp", "cpp/*.h", "cpp/*.hpp"],
        cwd=ROOT,
        capture_output=True,
    )
    if result.returncode:
        print(result.stderr.decode(errors="replace"), file=sys.stderr, end="")
        return result.returncode
    files = [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]
    if not files:
        print("No tracked C++ files to format.")
        return 0
    mode = ["--dry-run", "--Werror"] if args.check else ["-i"]
    print(
        "{0} {1} C++ files with clang-format {2}.".format(
            "Checking" if args.check else "Formatting", len(files), CLANG_FORMAT_VERSION
        ),
        flush=True,
    )
    return subprocess.run(
        [
            uvx,
            "--from",
            "clang-format==" + CLANG_FORMAT_VERSION,
            "clang-format",
            *mode,
            "--",
            *files,
        ],
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
