"""Shared command-line parsing, execution, and worker completion receipts."""

import argparse
from collections import namedtuple
import json
import os
import re
import sys

from .errors import ExportError, ExportFailure, SelectionError
from .models import ExportResult, Selection
from .outputs import OutputOptions, atomic_output

CliRequest = namedtuple(
    "CliRequest", "odb_file mode selection outputs write_history jobs"
)


def _positive_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a positive integer")
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def build_parser(parallel=False):
    parser = argparse.ArgumentParser(
        prog="python -m odb2vtk_core" + (".parallel" if parallel else ""),
        description="Convert Abaqus ODB data to VTU, PVD, JSON, and CSV.",
    )
    parser.add_argument(
        "--header",
        required=True,
        type=int,
        choices=(0, 1),
        help="1 writes header JSON; 0 exports the requested data",
    )
    parser.add_argument("--instance", nargs="+", help="selected instance names")
    parser.add_argument("--step", nargs="+", help="step/frame lists, e.g. 'Step-1:0,1'")
    parser.add_argument("--odbFile", required=True, help="input ODB path")
    parser.add_argument(
        "--suffix", default="", help="suffix appended to the output name"
    )
    parser.add_argument(
        "--writeHistory",
        type=int,
        choices=(0, 1),
        default=0,
        help="also export history CSV once",
    )
    parser.add_argument(
        "--writePVD",
        type=int,
        choices=(0, 1),
        default=0,
        help="1 indexes existing VTUs instead of converting frames",
    )
    if parallel:
        parser.add_argument(
            "--jobs",
            type=_positive_int,
            default=os.cpu_count() or 1,
            help="maximum concurrent Abaqus workers",
        )
    return parser


def parse_selection(instances, tokens):
    if not instances:
        raise SelectionError("--instance is required when --header is 0")
    if not tokens:
        raise SelectionError("--step is required when --header is 0")
    pairs = []
    for token in tokens:
        name, separator, text = token.rpartition(":")
        if not separator or not name or not re.fullmatch(r"[0-9]+(?:,[0-9]+)*", text):
            raise SelectionError(
                "Invalid --step {0!r}; use 'step_name:0,1,2'".format(token)
            )
        pairs.append((name, [int(value) for value in text.split(",")]))
    return Selection(instances, pairs)


def parse_request(argv=None, parallel=False):
    parser = build_parser(parallel)
    args = parser.parse_args(argv)
    path = os.path.abspath(args.odbFile)
    if not os.path.isfile(path):
        parser.error("ODB file does not exist or is not a file: {0}".format(path))
    try:
        outputs = OutputOptions.from_odb(path, args.suffix, write_pvd=False)
        if args.header:
            return CliRequest(
                path, "header", None, outputs, False, getattr(args, "jobs", 1)
            )
        selection = parse_selection(args.instance, args.step)
    except (ExportError, ValueError) as error:
        parser.error(str(error))
    return CliRequest(
        path,
        "collection" if args.writePVD else "frames",
        selection,
        outputs,
        bool(args.writeHistory),
        getattr(args, "jobs", 1),
    )


def _merge(results):
    return ExportResult(
        tuple(path for result in results for path in result.paths),
        tuple(frame for result in results for frame in result.frames),
        tuple(item for result in results for item in result.diagnostics),
    )


def execute_request(request, source_factory=None, progress=None, validate_only=False):
    """Execute a parsed request and close its source before reporting success."""
    from .converter import Converter
    from .source import AbaqusSource

    source_factory = AbaqusSource.open if source_factory is None else source_factory
    results = []
    try:
        with source_factory(request.odb_file) as source:
            converter = Converter(source, progress=progress)
            if request.mode == "header":
                if validate_only:
                    converter.inspect()
                else:
                    results.append(converter.export_header(request.outputs))
            else:
                if request.mode == "collection":
                    converter.validate_collection(request.selection, request.outputs)
                else:
                    converter.validate_frames(request.selection, request.outputs)
                if request.write_history:
                    converter.validate_history(request.selection, request.outputs)
                if not validate_only:
                    if request.write_history:
                        results.append(
                            converter.export_history(request.selection, request.outputs)
                        )
                    if request.mode == "collection":
                        results.append(
                            converter.export_collection(
                                request.selection, request.outputs
                            )
                        )
                    else:
                        results.append(
                            converter.export_frames(request.selection, request.outputs)
                        )
    except Exception as error:
        if results:
            partial = results + (
                [error.result] if isinstance(error, ExportFailure) else []
            )
            raise ExportFailure(str(error), _merge(partial), error)
        raise
    return _merge(results)


def _progress(event):
    print("Completed: {0}".format(event.path))


def _error_message(error):
    if isinstance(error, ImportError) and getattr(error, "name", None) in (
        "odbAccess",
        "abaqusConstants",
    ):
        return "Abaqus modules are unavailable; run this script with 'abaqus python'."
    return str(error)


def main(argv=None, source_factory=None):
    """Return 0 on success, 2 for arguments/selections, or 1 for runtime failure."""
    try:
        request = parse_request(argv)
        result = execute_request(request, source_factory, progress=_progress)
        for diagnostic in result.diagnostics:
            print(
                "Omitted {0}: {1}".format(diagnostic.field, diagnostic.message),
                file=sys.stderr,
            )
        return 0
    except SystemExit as error:
        return error.code
    except SelectionError as error:
        print("odb2vtk: {0}".format(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("odb2vtk: interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        print("odb2vtk: {0}".format(_error_message(error)), file=sys.stderr)
        if isinstance(error, ExportFailure) and error.result.paths:
            print(
                "Completed before failure: {0}".format(", ".join(error.result.paths)),
                file=sys.stderr,
            )
        return 1


def request_payload(request, validate_only=False):
    return {
        "version": 1,
        "odb_file": request.odb_file,
        "mode": request.mode,
        "selection": None if request.selection is None else request.selection._asdict(),
        "outputs": request.outputs._asdict(),
        "write_history": request.write_history,
        "validate_only": validate_only,
    }


def _decode_request(payload):
    if payload.get("version") != 1 or payload.get("mode") not in (
        "header",
        "frames",
        "collection",
    ):
        raise ValueError("Invalid worker request")
    selection = payload["selection"]
    selection = (
        None
        if selection is None
        else Selection(selection["instances"], selection["steps"])
    )
    if payload["mode"] != "header" and selection is None:
        raise SelectionError("Worker request requires a selection")
    return CliRequest(
        payload["odb_file"],
        payload["mode"],
        selection,
        OutputOptions(**payload["outputs"]),
        bool(payload["write_history"]),
        1,
    )


def worker_main(request_file, result_file, source_factory=None):
    """Internal JSON protocol: receipts remain authoritative if a launcher masks exits."""
    result = _merge([])
    code, message = 0, ""
    try:
        with open(request_file, encoding="utf-8") as stream:
            payload = json.load(stream)
        result = execute_request(
            _decode_request(payload),
            source_factory,
            validate_only=bool(payload.get("validate_only", False)),
        )
    except SelectionError as error:
        code, message = 2, str(error)
    except KeyboardInterrupt:
        code, message = 130, "interrupted"
    except Exception as error:
        code, message = 1, _error_message(error)
        if isinstance(error, ExportFailure):
            result = error.result
    receipt = {
        "version": 1,
        "code": code,
        "error": message,
        "paths": list(result.paths),
        "frames": [frame._asdict() for frame in result.frames],
        "diagnostics": [item._asdict() for item in result.diagnostics],
    }
    with atomic_output(result_file) as stream:
        json.dump(receipt, stream)
    if code:
        print("odb2vtk worker: {0}".format(message), file=sys.stderr)
    return code
