"""Run once in a fresh Abaqus Python process; no timing assertions in CI.

Compare the current exporter with a saved pre-refactor module and its utilities.
Timing excludes imports/SDK startup, includes open, map construction and VTUs.
Peak RSS includes imports/SDK, and is not a Python allocation measurement.
"""

import argparse
import contextlib
import ctypes
import importlib
import io
import json
import os
from pathlib import Path
import sys
import time


def peak_rss():
    if os.name != "nt":
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
            (name, ctypes.c_size_t)
            for name in (
                "PeakWorkingSetSize",
                "WorkingSetSize",
                "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage",
                "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage",
                "PagefileUsage",
                "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess
    handle.restype = ctypes.c_void_p
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    if not query(handle(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.PeakWorkingSetSize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odb", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--step", default="Step-1")
    parser.add_argument("--frames", default="0,1")
    parser.add_argument("--suffix", required=True)
    parser.add_argument("--baseline-dir")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    frames = tuple(int(value) for value in args.frames.split(","))
    if args.baseline_dir:
        sys.path.insert(0, args.baseline_dir)
        module = importlib.import_module("baseline_odb2vtk")
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from odb2vtk_core import AbaqusSource, Converter, OutputOptions, Selection

    # The old module imports the SDK eagerly; the new adapter imports it lazily.
    # Warm both explicitly so neither import policy biases export-only timing.
    importlib.import_module("odbAccess")
    importlib.import_module("abaqusConstants")
    start_peak = peak_rss()
    start = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        if args.baseline_dir:
            converter = module.ODB2VTK(args.odb, args.suffix)
            try:
                converter.ReadArgs([args.instance], {args.step: frames})
                converter.ConstructMap()
                converter.WriteVTUFiles()
            finally:
                converter.odb.odb.close()
        else:
            with AbaqusSource.open(args.odb) as source:
                Converter(source).export_frames(
                    Selection([args.instance], {args.step: frames}),
                    OutputOptions.from_odb(args.odb, args.suffix, write_pvd=False),
                )
    result = dict(
        implementation="baseline" if args.baseline_dir else "current",
        odb=args.odb,
        frames=len(frames),
        seconds=time.perf_counter() - start,
        peak_rss_bytes=peak_rss(),
        start_peak_rss_bytes=start_peak,
        python=sys.version,
    )
    Path(args.report).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
