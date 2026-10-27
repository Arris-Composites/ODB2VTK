"""Bounded Abaqus workers with preflight validation and verified completion."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid

from .cli import parse_request, request_payload
from .errors import ExportError
from .models import Diagnostic, ExportResult, FrameExport, Selection
from .outputs import ensure_directory

_BOOTSTRAP = """import os
import sys
sys.path.insert(0, os.environ["ODB2VTK_PYTHON_DIR"])
from odb2vtk_core.cli import worker_main
sys.exit(worker_main(os.environ["ODB2VTK_JOB_FILE"], os.environ["ODB2VTK_RESULT_FILE"]))
"""


class WorkerError(ExportError):
    def __init__(self, message, code=1, completed_paths=()):
        super(WorkerError, self).__init__(message)
        self.code = code
        self.completed_paths = tuple(completed_paths)


def expected_paths(request, validate_only=False):
    if validate_only:
        return ()
    if request.mode == "header":
        return (request.outputs.header_path,)
    history = (request.outputs.history_path,) if request.write_history else ()
    if request.mode == "collection":
        return history + (request.outputs.collection_path,)
    return history + tuple(
        request.outputs.frame_path(step, frame)
        for step, frames in request.selection.steps
        for frame in frames
    )


class AbaqusWorker(object):
    """Launch only a fixed bootstrap command; request data stays out of the shell.

    Receipts are required even for exit 0: vendor launchers may mask Python exit
    statuses. Every job uses fresh request/receipt paths, so old files cannot
    establish success for a new invocation.
    """

    def __init__(self, workspace, command=None, launch=None):
        if command is None:
            launcher = shutil.which("abaqus")
            if launcher is None:
                raise WorkerError("Abaqus command was not found on PATH")
            command = (launcher, "python")
        self.command = tuple(command)
        self.workspace = workspace
        self.launch = subprocess.run if launch is None else launch
        self.python_directory = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        with open(
            os.path.join(workspace, "worker.py"), "w", encoding="utf-8"
        ) as stream:
            stream.write(_BOOTSTRAP)

    def __call__(self, request, validate_only=False):
        identifier = uuid.uuid4().hex
        request_file = os.path.join(self.workspace, identifier + ".request.json")
        result_file = os.path.join(self.workspace, identifier + ".result.json")
        with open(request_file, "w", encoding="utf-8") as stream:
            json.dump(request_payload(request, validate_only), stream)
        environment = os.environ.copy()
        environment.update(
            ODB2VTK_PYTHON_DIR=self.python_directory,
            ODB2VTK_JOB_FILE=request_file,
            ODB2VTK_RESULT_FILE=result_file,
        )
        try:
            process = self.launch(
                list(self.command) + ["worker.py"],
                cwd=self.workspace,
                env=environment,
                shell=False,
                capture_output=True,
                text=True,
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except OSError as error:
            raise WorkerError("Cannot launch Abaqus: {0}".format(error))
        try:
            with open(result_file, encoding="utf-8") as stream:
                receipt = json.load(stream)
        except (OSError, ValueError) as error:
            details = (process.stderr or process.stdout or str(error))[-2000:]
            raise WorkerError(
                "Abaqus worker did not produce a valid completion receipt: {0}".format(
                    details
                )
            )
        if (
            not isinstance(receipt, dict)
            or receipt.get("version") != 1
            or type(receipt.get("code")) is not int
        ):
            raise WorkerError("Abaqus worker returned an invalid completion receipt")
        paths = receipt.get("paths")
        if not isinstance(paths, list) or any(
            not isinstance(path, str) for path in paths
        ):
            raise WorkerError("Abaqus worker returned invalid output paths")
        if process.returncode != 0 or receipt["code"] != 0:
            message = (
                receipt.get("error")
                or process.stderr
                or "process exited with {0}".format(process.returncode)
            )
            raise WorkerError(
                "Abaqus worker failed: {0}".format(message), receipt["code"] or 1, paths
            )
        expected = expected_paths(request, validate_only)
        normalized = lambda path: os.path.normcase(os.path.abspath(path))
        if len(paths) != len(expected) or set(map(normalized, paths)) != set(
            map(normalized, expected)
        ):
            raise WorkerError("Abaqus worker did not report all requested output files")
        if any(not os.path.isfile(path) for path in expected):
            raise WorkerError("Abaqus worker reported an output file that is missing")
        try:
            return ExportResult(
                tuple(paths),
                tuple(FrameExport(**frame) for frame in receipt["frames"]),
                tuple(Diagnostic(**item) for item in receipt["diagnostics"]),
            )
        except (KeyError, TypeError, ValueError):
            raise WorkerError("Abaqus worker returned invalid export metadata")


def run_parallel(request, worker, progress=None):
    """Preflight once, drain failed workers, and publish a collection last."""
    if request.mode != "frames":
        result = worker(request)
        if progress is not None:
            try:
                progress(result)
            except Exception as error:
                raise WorkerError(str(error), completed_paths=result.paths)
        return result
    worker(
        request._replace(outputs=request.outputs._replace(write_pvd=True)),
        validate_only=True,
    )
    ensure_directory(request.outputs.data_directory)
    tasks = [
        request._replace(
            selection=Selection(request.selection.instances, ((step, (frame,)),)),
            write_history=False,
            jobs=1,
        )
        for step, frames in request.selection.steps
        for frame in frames
    ]
    results = [None] * len(tasks)
    first_error = None
    # Threads coordinate subprocesses; numerical conversion happens in Abaqus.
    # Exiting the executor waits for already-running writers before returning.
    with ThreadPoolExecutor(max_workers=min(request.jobs, len(tasks))) as pool:
        futures = {pool.submit(worker, task): index for index, task in enumerate(tasks)}
        try:
            for future in as_completed(futures):
                if future.cancelled():
                    continue
                try:
                    result = future.result()
                    results[futures[future]] = result
                    if progress is not None:
                        progress(result)
                except Exception as error:
                    if first_error is None:
                        first_error = error
                    for pending in futures:
                        pending.cancel()
        finally:
            # Also cancel queued work when the caller interrupts the iterator.
            for pending in futures:
                pending.cancel()
    completed = [
        path for result in results if result is not None for path in result.paths
    ]
    if first_error is not None:
        if isinstance(first_error, WorkerError):
            first_error.completed_paths = tuple(completed) + first_error.completed_paths
            raise first_error
        raise WorkerError(str(first_error), completed_paths=completed)
    for task, result in zip(tasks, results):
        if result is None or any(
            not os.path.isfile(path) for path in expected_paths(task)
        ):
            raise WorkerError(
                "A completed frame worker has a missing VTU", completed_paths=completed
            )
    final_request = request._replace(mode="collection", jobs=1)
    final = None
    try:
        final = worker(final_request)
        if progress is not None:
            progress(final)
    except WorkerError as error:
        error.completed_paths = tuple(completed) + error.completed_paths
        raise
    except Exception as error:
        published = tuple(completed) + (() if final is None else final.paths)
        raise WorkerError(str(error), completed_paths=published)
    paths = tuple(completed) + final.paths
    return ExportResult(
        paths,
        tuple(frame for result in results for frame in result.frames),
        tuple(item for result in results for item in result.diagnostics)
        + final.diagnostics,
    )


def _report_completed(result):
    for path in result.paths:
        print("Completed: {0}".format(path))


def main(argv=None, worker_factory=None):
    try:
        request = parse_request(argv, parallel=True)
        with tempfile.TemporaryDirectory(prefix="odb2vtk-workers-") as workspace:
            worker = (
                AbaqusWorker(workspace)
                if worker_factory is None
                else worker_factory(workspace)
            )
            result = run_parallel(request, worker, progress=_report_completed)
        print("Completed {0} output file(s).".format(len(result.paths)))
        for diagnostic in result.diagnostics:
            print(
                "Omitted {0}: {1}".format(diagnostic.field, diagnostic.message),
                file=sys.stderr,
            )
        return 0
    except SystemExit as error:
        return error.code
    except KeyboardInterrupt:
        print("odb2vtk parallel: interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        print("odb2vtk parallel: {0}".format(error), file=sys.stderr)
        if isinstance(error, WorkerError) and error.completed_paths:
            print(
                "{0} completed file(s) remain in the output directory.".format(
                    len(error.completed_paths)
                ),
                file=sys.stderr,
            )
        return 2 if isinstance(error, WorkerError) and error.code == 2 else 1
