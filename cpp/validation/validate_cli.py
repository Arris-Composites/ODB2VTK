"""Verify real C++/Abaqus-Python CLI processes and matching exported files.

Run in a NumPy/VTK environment with Abaqus and SDK runtime DLLs on PATH.
Each implementation receives an identical disposable input copy.
"""

import argparse
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from compare_exports import compare


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def locked_file(path):
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = create(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True)
    parser.add_argument("--odb", required=True)
    parser.add_argument("--instance", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", default="1,0")
    parser.add_argument(
        "--steps",
        nargs="+",
        help="ordered step tokens; overrides --frames in successful data cases",
    )
    parser.add_argument("--abaqus", default=shutil.which("abaqus"))
    args = parser.parse_args()
    if not args.abaqus:
        parser.error("Abaqus launcher not found")
    output = Path(args.output).resolve()
    odb = Path(args.odb).resolve()
    original_hash = digest(odb)
    inputs = {}
    for implementation in ("cpp", "python"):
        directory = output / implementation / "input with & % spaces"
        directory.mkdir(parents=True, exist_ok=True)
        inputs[implementation] = directory / odb.name
        shutil.copyfile(odb, inputs[implementation])
        assert digest(inputs[implementation]) == original_hash
    name = odb.name.split(".")[0]
    selected_steps = args.steps or ["Step-1:" + args.frames]
    records = []
    counter = 0

    def run(implementation, label, arguments, expected):
        nonlocal counter
        counter += 1
        if implementation == "cpp":
            process = subprocess.run(
                [args.exe, *arguments], capture_output=True, timeout=120
            )
            result = dict(
                code=process.returncode,
                stdout=process.stdout.decode("utf-8", errors="replace"),
                stderr=process.stderr.decode("utf-8", errors="replace"),
            )
        else:
            report = output / ("receipt-" + str(counter) + ".json")
            report.unlink(missing_ok=True)
            # The Abaqus Windows batch launcher best-fit maps Greek mu to the
            # micro sign. Preserve exact argv values for the real Python parser.
            argument_file = output / ("arguments-" + str(counter) + ".json")
            argument_file.write_text(json.dumps(arguments), encoding="utf-8")
            process = subprocess.run(
                [
                    args.abaqus,
                    "python",
                    str(Path(__file__).with_name("python_cli_reference.py")),
                    str(report),
                    "--arguments-file",
                    str(argument_file),
                ],
                capture_output=True,
                timeout=120,
            )
            assert report.is_file(), (
                label,
                process.returncode,
                process.stdout,
                process.stderr,
            )
            result = json.loads(report.read_text(encoding="utf-8"))
        assert result["code"] == expected, (implementation, label, result)
        if expected:
            assert result["stderr"], (implementation, label, "No error diagnostic")
        records.append(
            dict(
                implementation=implementation,
                case=label,
                expected_code=expected,
                actual_code=result["code"],
            )
        )
        return result

    def command(implementation, suffix, frames=None):
        return [
            "--header",
            "0",
            "--odbFile",
            str(inputs[implementation]),
            "--instance",
            *args.instance,
            "--step",
            *(selected_steps if frames is None else ["Step-1:" + frames]),
            "--suffix",
            suffix,
        ]

    comparisons = []
    for implementation in inputs:
        run(implementation, "help", ["--help"], 0)
        run(
            implementation,
            "header",
            [
                "--header",
                "1",
                "--odbFile",
                str(inputs[implementation]),
                "--suffix",
                "_header",
                "--step",
                "ignored",
            ],
            0,
        )
    for encoding in ("ascii", "binary"):
        suffix = "_" + encoding + "_μ space"
        paths = {}
        for implementation in inputs:
            flags = command(implementation, suffix) + ["--writeHistory", "1"]
            if encoding == "binary":
                flags += ["--format", "binary"]
            run(implementation, encoding + "_frames_history", flags, 0)
            directory = inputs[implementation].parent / (name + suffix)
            history, pvd = directory / (name + suffix + ".csv"), directory / (
                name + suffix + ".pvd"
            )
            vtus = [
                directory / (token.rpartition(":")[0] + "_" + str(int(frame)) + ".vtu")
                for token in selected_steps
                for frame in token.rpartition(":")[2].split(",")
            ]
            assert history.is_file() and all(path.is_file() for path in vtus)
            assert not pvd.exists(), "Normal CLI frame export unexpectedly wrote a PVD"
            states = [(digest(path), path.stat().st_mtime_ns) for path in vtus]
            run(
                implementation,
                encoding + "_collection_only",
                command(implementation, suffix) + ["--writePVD", "1"],
                0,
            )
            assert states == [
                (digest(path), path.stat().st_mtime_ns) for path in vtus
            ], "Collection rewrote frame data"
            paths[implementation] = dict(
                vtus=vtus,
                history=history,
                pvd=pvd,
                header=inputs[implementation].parent / (name + "_header.json"),
            )
        reference = dict(
            paths=[
                str(paths["python"]["history"]),
                *map(str, paths["python"]["vtus"]),
                str(paths["python"]["pvd"]),
            ]
        )
        result = compare(
            reference,
            paths["cpp"]["vtus"],
            paths["python"]["header"],
            paths["cpp"]["header"],
            paths["cpp"]["history"],
            paths["cpp"]["pvd"],
        )
        assert result["parity"], result
        result["format"] = encoding
        comparisons.append(result)
    for implementation, file in inputs.items():
        run(
            implementation,
            "default_frames",
            command(implementation, "_defaults", "0"),
            0,
        )
        default_dir = file.parent / (name + "_defaults")
        assert sorted(path.suffix for path in default_dir.iterdir()) == [".vtu"]
        assert b'format="ascii"' in next(default_dir.iterdir()).read_bytes()
        common = ["--header", "1", "--odbFile", str(file)]
        invalid = [
            ("missing_header", ["--odbFile", str(file)]),
            ("missing_value", ["--header", "1", "--odbFile"]),
            ("unknown_flag", common + ["--unknown", "1"]),
            ("extra_value", common + ["extra"]),
            ("bad_format", common + ["--format", "zip"]),
            ("bad_history", common + ["--writeHistory", "2"]),
            ("bad_collection", common + ["--writePVD", "2"]),
            ("bad_suffix", common + ["--suffix", "../escape"]),
            ("no_selection", ["--header", "0", "--odbFile", str(file)]),
            ("ranged_frames", command(implementation, "_bad", "0-1")),
            ("duplicate_frames", command(implementation, "_bad", "0,0")),
            ("out_of_range", command(implementation, "_bad", "999999")),
        ]
        for label, arguments in invalid:
            run(implementation, label, arguments, 2)
        assert not (file.parent / (name + "_bad")).exists()
        run(
            implementation,
            "missing_collection",
            command(implementation, "_missing")
            + ["--writeHistory", "1", "--writePVD", "1"],
            1,
        )
        assert not (file.parent / (name + "_missing")).exists()
        conflict = file.parent / (name + "_conflict")
        (conflict / "Step-1_0.vtu").mkdir(parents=True, exist_ok=True)
        run(
            implementation,
            "preflight_conflict",
            command(implementation, "_conflict", "0") + ["--writeHistory", "1"],
            1,
        )
        assert not (conflict / (name + "_conflict.csv")).exists()
        corrupt = file.parent / "corrupt.odb"
        corrupt.write_bytes(b"Deliberate invalid ODB fixture\n")
        run(
            implementation,
            "invalid_odb",
            ["--header", "1", "--odbFile", str(corrupt)],
            1,
        )
        if os.name == "nt" and len(args.frames.split(",")) > 1:
            suffix = "_partial"
            directory = file.parent / (name + suffix)
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / "Step-1_1.vtu"
            target.write_bytes(b"previous frame")
            with locked_file(target):
                result = run(
                    implementation,
                    "locked_second_frame",
                    command(implementation, suffix, "0,1") + ["--writeHistory", "1"],
                    1,
                )
            assert target.read_bytes() == b"previous frame"
            assert "Completed before failure:" in result["stderr"]
            assert (
                "Step-1_0.vtu" in result["stderr"]
                and name + suffix + ".csv" in result["stderr"]
            )
            assert (directory / "Step-1_0.vtu").is_file()
        assert digest(file) == original_hash
    # These intentionally stricter native rules follow the alignment plan.
    run(
        "cpp",
        "repeated_flag",
        ["--header", "1", "--header", "1", "--odbFile", str(inputs["cpp"])],
        2,
    )
    run("cpp", "abbreviated_flag", ["--header", "1", "--odb", str(inputs["cpp"])], 2)
    assert digest(odb) == original_hash
    assert not list(output.rglob(".odb2vtk-*.tmp"))
    result = dict(
        passed=True,
        input_sha256=original_hash,
        input_unchanged=True,
        cases=records,
        comparisons=comparisons,
        default_ascii=True,
        default_no_history_or_collection=True,
        ordered_steps=selected_steps,
        collection_preserves_vtu_bytes_and_mtime=True,
        unicode_suffix_and_spaced_paths=True,
    )
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            dict(
                passed=True,
                process_cases=len(records),
                frames_checked=sum(item["frames_checked"] for item in comparisons),
            )
        )
    )


if __name__ == "__main__":
    main()
