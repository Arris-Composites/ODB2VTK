"""Run the public Python CLI and persist its status despite Abaqus launcher exits."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from odb2vtk_core.cli import main

if __name__ == "__main__":
    report = Path(sys.argv[1])
    arguments = (
        json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
        if len(sys.argv) == 4 and sys.argv[2] == "--arguments-file"
        else sys.argv[2:]
    )
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(arguments)
    report.write_text(
        json.dumps(dict(code=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())),
        encoding="utf-8",
    )
    raise SystemExit(code)
