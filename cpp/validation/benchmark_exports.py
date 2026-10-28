"""Alternate fresh Python/native exports, verify parity, and measure warm VTK reads.

Primary samples disable phase clocks. Instrumented probes are separate. Inputs
and caches are warm; buffered writes are not fsync/durable-storage measurements.
Requires NumPy/VTK, Abaqus on PATH, and native SDK runtime DLLs on PATH.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time

from compare_exports import compare, read


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpp-profile", required=True)
    parser.add_argument("--baseline-cpp-profile")
    parser.add_argument("--odb", required=True)
    parser.add_argument("--instance", nargs="+", required=True)
    parser.add_argument("--frames", default="0,1")
    parser.add_argument("--output", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--abaqus", default=shutil.which("abaqus"))
    args = parser.parse_args()
    if args.repeats < 3 or not args.abaqus:
        parser.error("Require at least three repeats and an Abaqus launcher")
    repo = Path(__file__).resolve().parents[2]
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    odb = Path(args.odb).resolve()
    input_hash = sha256(odb)
    implementations = ["python", "cpp"]
    if args.baseline_cpp_profile:
        implementations.insert(1, "cpp_baseline")
    binaries = {"cpp": str(Path(args.cpp_profile).resolve())}
    if args.baseline_cpp_profile:
        binaries["cpp_baseline"] = str(Path(args.baseline_cpp_profile).resolve())
    runs, probes, last = [], [], {}
    signatures = {}

    def run(implementation, encoding, sample, phases=False):
        report = output / (
            implementation + "-" + encoding + "-" + str(sample) + ".json"
        )
        report.unlink(missing_ok=True)
        # Separate deterministic output directories. Repeated runs replace the
        # same files, so measured writes have the same publication policy.
        suffix = "_phase5_" + implementation + "_" + encoding
        if implementation == "python":
            command = [
                args.abaqus,
                "python",
                str(repo / "python/validation/profile_exports.py"),
                "--odb",
                str(odb),
                "--instance",
                *args.instance,
                "--frames",
                args.frames,
                "--suffix",
                suffix,
                "--format",
                encoding,
                "--report",
                str(report),
                "--history",
            ]
        else:
            command = [
                binaries[implementation],
                str(odb),
                ",".join(args.instance),
                args.frames,
                suffix,
                encoding,
                str(report),
            ]
        if not phases:
            command.append("--no-phases")
        started = time.perf_counter()
        process = subprocess.run(command, capture_output=True, timeout=180)
        wall = time.perf_counter() - started
        assert process.returncode == 0 and not process.stderr, (
            command,
            process.returncode,
            process.stdout,
            process.stderr,
        )
        assert report.is_file(), (command, process.stdout)
        result = json.loads(report.read_text())
        result.update(
            implementation=implementation,
            sample=sample,
            process_wall_seconds=wall,
            outside_workflow_seconds=wall - result["seconds"],
        )
        assert result["outside_workflow_seconds"] >= 0
        paths = list(map(Path, result["paths"]))
        assert result["output_bytes"] == sum(path.stat().st_size for path in paths)
        signature = {path.name: sha256(path) for path in paths}
        key = (implementation, encoding)
        if key in signatures:
            assert signature == signatures[key], (key, "Nondeterministic output")
        signatures[key] = signature
        if phases:
            assert (
                abs(sum(result["phases_seconds"].values()) - result["seconds"]) < 1e-6
            )
            assert all(value >= 0 for value in result["phases_seconds"].values())
            probes.append(result)
        elif sample != "warmup":
            runs.append(result)
        last[key] = result
        assert sha256(odb) == input_hash
        print(
            implementation,
            encoding,
            sample,
            "workflow=%.6fs process=%.6fs" % (result["seconds"], wall),
            flush=True,
        )

    for encoding in ("ascii", "binary"):
        for implementation in implementations:
            run(implementation, encoding, "warmup")
    for sample in range(args.repeats):
        formats = ("ascii", "binary") if sample % 2 == 0 else ("binary", "ascii")
        order = implementations if sample % 2 == 0 else list(reversed(implementations))
        for encoding in formats:
            for implementation in order:
                run(implementation, encoding, sample)
    for encoding in ("ascii", "binary"):
        for implementation in implementations:
            run(implementation, encoding, "phases", phases=True)
    parity = []
    for encoding in ("ascii", "binary"):
        reference = last[("python", encoding)]
        for implementation in implementations:
            if implementation == "python":
                continue
            candidate = last[(implementation, encoding)]
            frames = [path for path in candidate["paths"] if path.endswith(".vtu")]
            history = next(path for path in candidate["paths"] if path.endswith(".csv"))
            pvd = next(path for path in candidate["paths"] if path.endswith(".pvd"))
            result = compare(reference, frames, cpp_history=history, cpp_pvd=pvd)
            assert result["parity"], result
            result.update(implementation=implementation, format=encoding)
            parity.append(result)
    read_samples = {key: [] for key in last}
    for sample in range(args.repeats):
        order = list(last) if sample % 2 == 0 else list(reversed(last))
        for key in order:
            started = time.perf_counter()
            for path in last[key]["paths"]:
                if not path.endswith(".vtu"):
                    continue
                grid, messages = read(path)
                assert not messages, messages
                assert grid.GetNumberOfPoints() > 0 and grid.GetNumberOfCells() > 0
                del grid
            read_samples[key].append(time.perf_counter() - started)
    summaries = []
    for implementation in implementations:
        for encoding in ("ascii", "binary"):
            samples = [
                run
                for run in runs
                if run["implementation"] == implementation
                and run["vtu_format"] == encoding
            ]
            values = [run["seconds"] for run in samples]
            summaries.append(
                dict(
                    implementation=implementation,
                    format=encoding,
                    workflow_median_seconds=statistics.median(values),
                    workflow_min_seconds=min(values),
                    workflow_max_seconds=max(values),
                    process_wall_median_seconds=statistics.median(
                        run["process_wall_seconds"] for run in samples
                    ),
                    outside_workflow_median_seconds=statistics.median(
                        run["outside_workflow_seconds"] for run in samples
                    ),
                    peak_rss_median_bytes=statistics.median(
                        run["peak_rss_bytes"] for run in samples
                    ),
                    output_bytes=samples[0]["output_bytes"],
                    warm_reader_median_seconds=statistics.median(
                        read_samples[(implementation, encoding)]
                    ),
                )
            )
    # Strip machine-specific output paths from the portable report. Per-run raw
    # reports remain in --output for local inspection and reproducibility.
    for run_record in runs + probes:
        run_record["paths"] = [Path(path).name for path in run_record["paths"]]
        if "odb" in run_record:
            run_record["odb"] = odb.name
        if run_record.get("cprofile"):
            run_record["cprofile"] = Path(run_record["cprofile"]).name
    result = dict(
        odb=odb.name,
        odb_sha256=input_hash,
        input_unchanged=True,
        platform=platform.platform(),
        frames=args.frames,
        instances=args.instance,
        repeats=args.repeats,
        warmup_processes=2 * len(implementations),
        cache_conditions="Warm input and filesystem cache; buffered writes, no fsync; one discarded warmup per implementation/format",
        timing_scope="Workflow includes open/history/frames/PVD/close; process wall additionally includes launch/imports/report/shutdown",
        native_startup_note="Native API initialization is inside odb_open; Python SDK/package imports are outside its workflow timer",
        executable_sha256={name: sha256(Path(path)) for name, path in binaries.items()},
        summaries=summaries,
        parity=parity,
        samples=runs,
        phase_probes=probes,
        warm_reader_samples={
            name + "/" + encoding: values
            for (name, encoding), values in read_samples.items()
        },
    )
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(summaries, indent=2), flush=True)


if __name__ == "__main__":
    main()
