"""Measure exclusive conversion phases in a fresh Abaqus Python process.

Instrumentation is local to this validation script. Generator advancement is
timed separately from its caller, and nested timings are subtracted from parents.
Use --no-phases for a control run and --cprofile PATH for a separate hotspot run.
"""

import argparse
from collections import defaultdict
from contextlib import ExitStack, contextmanager
from functools import wraps
import importlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

from benchmark_exports import peak_rss

PHASES = (
    "odb_open",
    "validation",
    "mesh_preparation",
    "field_discovery",
    "field_read",
    "field_assembly",
    "vtu_serialization",
    "file_publication",
    "history",
    "collection",
    "odb_close",
    "orchestration",
)


class PhaseClock:
    def __init__(self):
        self.totals = defaultdict(float)
        self.details = defaultdict(lambda: defaultdict(float))
        self.stack = []
        self.frame = None
        self.field = None
        self.frames = []
        self.mesh = None

    @contextmanager
    def measure(self, phase, key=None):
        entry = [time.perf_counter(), 0.0]
        self.stack.append(entry)
        try:
            yield
        finally:
            elapsed = time.perf_counter() - entry[0]
            exclusive = elapsed - entry[1]
            self.stack.pop()
            self.totals[phase] += exclusive
            if key is not None:
                self.details[key][phase] += exclusive
            if self.stack:
                self.stack[-1][1] += elapsed

    def call(self, function, phase):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with self.measure(phase):
                return function(*args, **kwargs)

        return wrapped

    def iterate(self, function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            # Time creation too: field_blocks performs some native queries
            # before returning its iterator. Never keep a span open over yield.
            with self.measure("field_read", self.field):
                iterator = iter(function(*args, **kwargs))
            while True:
                try:
                    with self.measure("field_read", self.field):
                        value = next(iterator)
                except StopIteration:
                    return
                yield value

        return wrapped


@contextmanager
def instrument(clock, converter, source):
    from odb2vtk_core import converter as module, writers

    with ExitStack() as patches:
        for name, phase in (
            ("validate_frames", "validation"),
            ("validate_history", "validation"),
            ("_field_plans", "field_discovery"),
            ("_publish_collection", "collection"),
            ("export_history", "history"),
        ):
            patches.enter_context(
                patch.object(
                    converter, name, clock.call(getattr(converter, name), phase)
                )
            )
        for name in ("field_blocks", "orientation_blocks"):
            patches.enter_context(
                patch.object(source, name, clock.iterate(getattr(source, name)))
            )

        prepare_mesh = converter._prepare_mesh

        def mesh(*args):
            with clock.measure("mesh_preparation"):
                result = prepare_mesh(*args)
                clock.mesh = dict(
                    points=len(result.mesh.points), cells=len(result.mesh.offsets)
                )
                return result

        patches.enter_context(patch.object(converter, "_prepare_mesh", mesh))

        read_plan = converter._read_plan

        def field(plan, step, frame, prepared):
            previous = clock.field
            clock.field = "{0}:{1}/{2}".format(step, frame, plan.name)
            try:
                with clock.measure("field_assembly", clock.field):
                    return read_plan(plan, step, frame, prepared)
            finally:
                clock.field = previous

        patches.enter_context(patch.object(converter, "_read_plan", field))

        write_frame = converter._write_frame

        def frame(stream, step, index, *args):
            previous = clock.frame
            clock.frame = "{0}:{1}".format(step, index)
            started = time.perf_counter()
            try:
                with clock.measure("orchestration"):
                    return write_frame(stream, step, index, *args)
            finally:
                clock.frames.append(
                    dict(step=step, frame=index, seconds=time.perf_counter() - started)
                )
                clock.frame = previous

        patches.enter_context(patch.object(converter, "_write_frame", frame))

        write_array = writers.write_data_array

        def array(stream, field):
            with clock.measure(
                "vtu_serialization", "{0}/{1}".format(clock.frame, field.name)
            ):
                return write_array(stream, field)

        patches.enter_context(patch.object(writers, "write_data_array", array))
        patches.enter_context(
            patch.object(
                writers, "write_vtu", clock.call(writers.write_vtu, "vtu_serialization")
            )
        )
        if hasattr(module, "binary_writer"):
            binary = module.binary_writer
            patches.enter_context(
                patch.object(
                    binary,
                    "write_vtu",
                    clock.call(binary.write_vtu, "vtu_serialization"),
                )
            )
        if hasattr(writers, "serialized_mesh"):
            original_mesh = writers.serialized_mesh

            @contextmanager
            def serialized_mesh(*args, **kwargs):
                # Creation/closure happens outside write_vtu, but is still
                # serialization work. ExitStack preserves failure semantics.
                with ExitStack() as stack:
                    with clock.measure("vtu_serialization"):
                        result = stack.enter_context(original_mesh(*args, **kwargs))
                    try:
                        yield result
                    finally:
                        with clock.measure("vtu_serialization"):
                            stack.close()

            patches.enter_context(
                patch.object(writers, "serialized_mesh", serialized_mesh)
            )

        original_atomic = module.atomic_output

        @contextmanager
        def atomic(path, *args, **kwargs):
            manager = original_atomic(path, *args, **kwargs)
            with clock.measure("file_publication"):
                stream = manager.__enter__()
            try:
                yield stream
            except BaseException:
                error = sys.exc_info()
                with clock.measure("file_publication"):
                    suppress = manager.__exit__(*error)
                if not suppress:
                    raise
            else:
                with clock.measure("file_publication"):
                    manager.__exit__(None, None, None)

        patches.enter_context(patch.object(module, "atomic_output", atomic))
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--odb", required=True)
    parser.add_argument("--instance", required=True, nargs="+")
    parser.add_argument("--step", default="Step-1")
    parser.add_argument("--frames", default="0,1")
    parser.add_argument("--suffix", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--no-phases", action="store_true")
    parser.add_argument("--format", choices=("ascii", "binary"), default="ascii")
    parser.add_argument("--cprofile", help="optional separate cProfile output file")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    started = time.perf_counter()
    import numpy as np
    from odb2vtk_core import AbaqusSource, Converter, OutputOptions, Selection

    importlib.import_module("odbAccess")
    importlib.import_module("abaqusConstants")
    import_seconds = time.perf_counter() - started
    selection = Selection(
        args.instance, {args.step: tuple(int(v) for v in args.frames.split(","))}
    )
    # ASCII also supports historical baseline packages without the new option.
    options = {"vtu_format": "binary"} if args.format == "binary" else {}
    outputs = OutputOptions.from_odb(args.odb, args.suffix, write_pvd=True, **options)
    clock = PhaseClock()
    profiler = None
    if args.cprofile:
        import cProfile

        profiler = cProfile.Profile()
        profiler.enable()
    paths = []
    started = time.perf_counter()
    with ExitStack() as stack:
        if not args.no_phases:
            stack.enter_context(clock.measure("orchestration"))
        with clock.measure("odb_open"):
            source = AbaqusSource.open(args.odb)
        try:
            converter = Converter(source)
            if not args.no_phases:
                stack.enter_context(instrument(clock, converter, source))
            if args.history:
                paths.extend(converter.export_history(selection, outputs).paths)
            paths.extend(converter.export_frames(selection, outputs).paths)
        finally:
            with clock.measure("odb_close"):
                source.close()
    seconds = time.perf_counter() - started
    if profiler is not None:
        profiler.disable()
        profiler.dump_stats(args.cprofile)
    assert source.closed
    phases = None
    if not args.no_phases:
        measured = sum(clock.totals.values())
        assert abs(measured - seconds) < 0.001 + seconds * 0.001, (measured, seconds)
        # Account for the outer timer/context setup and teardown too. It is
        # bookkeeping, not part of any conversion phase.
        clock.totals["orchestration"] += seconds - measured
        phases = {name: clock.totals[name] for name in PHASES}
    result = dict(
        odb=str(Path(args.odb).resolve()),
        python=sys.version,
        numpy=np.__version__,
        vtu_format=args.format,
        instances=args.instance,
        frames=list(selection.steps),
        history=args.history,
        sdk_and_package_imports_seconds=import_seconds,
        seconds=seconds,
        phases_seconds=phases,
        fields_seconds=dict(clock.details),
        frame_body_seconds=clock.frames,
        mesh=clock.mesh,
        peak_rss_bytes=peak_rss(),
        output_bytes=sum(Path(p).stat().st_size for p in paths),
        paths=paths,
        cprofile=args.cprofile,
    )
    Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
    print(
        "{0:.6f} seconds; {1} bytes; report {2}".format(
            seconds, result["output_bytes"], args.report
        )
    )
    if phases is not None:
        for phase, elapsed in phases.items():
            print(
                "{0:24s} {1:10.6f} s {2:7.2f}%".format(
                    phase, elapsed, elapsed / seconds * 100
                )
            )


if __name__ == "__main__":
    main()
