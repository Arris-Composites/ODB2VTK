# Python CLI and parallel runner

Use the package entry points:

- `abaqus python -m odb2vtk_core` executes `odb2vtk_core.cli.main(argv)`.
- `python -m odb2vtk_core.parallel` executes `odb2vtk_core.parallel.main(argv)` under ordinary
  Python, with the Abaqus command available on `PATH`.

Both functions return status codes. The module entry points translate them to process
exits. Help and the host parallel coordinator use the standard library; NumPy and
Abaqus are loaded only when numerical/source operations need them.

## Commands

Run these from the repository's `python` directory (`cd python` from the repo
root). From another directory, put the absolute repository `python` directory on
`PYTHONPATH` for both the host and Abaqus interpreter. The old standalone scripts
and library wrappers have been removed; they are not supported aliases.
Quote paths, step names, instance names, and suffixes containing spaces.

Write header JSON:

```text
abaqus python -m odb2vtk_core --header 1 --odbFile "C:/simulation results/job.odb"
```

Convert frames and optionally history, without a PVD:

```text
abaqus python -m odb2vtk_core --header 0 --odbFile "C:/simulation results/job.odb" --instance "PART-1-1" --step "Step-1:0,1" --writeHistory 1 --suffix "_selected"
```

Index existing VTUs without converting them:

```text
abaqus python -m odb2vtk_core --header 0 --odbFile "C:/simulation results/job.odb" --instance "PART-1-1" --step "Step-1:0,1" --writePVD 1 --suffix "_selected"
```

Convert with at most two Abaqus workers, then export history once and write a PVD:

```text
python -m odb2vtk_core.parallel --header 0 --odbFile "C:/simulation results/job.odb" --instance "PART-1-1" --step "Step-1:0,1" --jobs 2 --writeHistory 1 --suffix "_parallel"
```

The parallel script also supports header-only and PVD-only requests. Its normal
frame mode always generates a collection after verified completion, preserving
the original runner's output contract. Single-process frame mode retains its
existing no-collection default.

## Shared validation and statuses

`--header`, `--writeHistory`, and `--writePVD` accept only `0` or `1`. Instance and
step flags require values. Python step syntax remains `name:0,1,2`; frame ranges
are not added in this refactor. Repeated steps, repeated instances, duplicate
frames, negative indices, malformed frame lists, and unknown flags are rejected.
Header mode ignores selection values, as before.

Source validation rejects unknown names and out-of-range frames. Header/PVD-only
modes do not construct a mesh. PVD-only mode now refuses missing references rather
than publishing a collection for files that were never exported. Output schemas,
suffix handling, and the existing first-dot ODB naming policy remain unchanged.

| Status | Meaning |
| --- | --- |
| `0` | Success, including header export and help |
| `2` | Argument or source-selection error |
| `1` | Source, serialization, publication, or worker failure |
| `130` | Caller interruption, after active work settles |

Runtime errors are concise stderr messages rather than tracebacks. Completed
paths are reported when a later operation fails. Syntactically invalid requests
are rejected before opening a source. Sources close on all executed paths.

**Vendor launcher limitation:** the local Abaqus 2025 Windows launcher returned
`0` for a Python probe that exited with `7`. These are the Python entry points'
statuses; a vendor launcher can mask them before the calling shell sees them.
The host parallel script checks structured completion receipts in addition to
process status and therefore detects this case. For shell automation requiring
reliable statuses on that installation, use the host runner, including `--jobs 1`
when serial execution is preferred.

## Parallel execution sequence

1. Parse and freeze the full selection and output options in the host process.
2. Run one Abaqus preflight for the full selection, including collection/history
   destination conflicts. This reads metadata and creates no conversion output.
3. Create the data directory, then launch one frame request per worker with a
   bounded concurrency of `min(--jobs, frame_count)`.
4. Require a successful process result, a successful completion receipt, the
   expected output-path list, and each actual VTU file.
5. After every worker finishes successfully, run the aggregate request once:
   optional history CSV, then collection generation.

The default job limit is the host CPU count, capped by selected frame count.
Threads coordinate external processes; numerical conversion runs in separate
Abaqus interpreters. Receipts and final results retain requested frame order even
when workers finish in a different order.

On worker failure, queued jobs are cancelled and already-running jobs are allowed
to finish before the runner returns. No collection stage is scheduled. Interrupts
also cancel queued work and drain active writers. Completed files remain available;
existing collection files are not replaced by a failed frame request. Publication
is atomic per file, with no rollback of completed files across the request.

## Worker transport

Each run has a temporary transport directory containing a fixed bootstrap script
and uniquely named JSON request/receipt files. The command line contains only
the resolved launcher, `python`, and `worker.py`. Paths, instances, selections,
and suffixes are transported as JSON; the bootstrap obtains transport/package
locations from its environment. User values are not interpolated into shell text.

The worker writes its receipt only after source closure. A zero launcher result
without a valid matching receipt is a failure, even if an old VTU already exists.
This design also avoids the batch argument-parsing pitfalls described in
[Python's subprocess documentation](https://docs.python.org/3.12/library/subprocess.html#security-considerations).

Transport artifacts are removed after worker processes finish. Original ODB
fixtures are never upgraded in place by the exporter.

## Verified paths and limits

Real tests covered spaces in code directories, ODB paths, and suffixes, plus
ampersands and literal percent characters. A `%TEMP%` sequence was preserved in
an output suffix. The SDK itself expanded a known `%PATH%` sequence inside an
input ODB filename, causing that literal filename to fail to open. JSON transport
preserved the original string; overriding native SDK path expansion is outside
this refactor. Avoid known `%ENV%` sequences in literal ODB input names on that
installation.

See [Phase 5 results](python-phase5-results.md) for duration and memory
measurements, and the [architecture guide](python-architecture.md) for supported
runtimes. This implementation was tested with Python 3.10/3.12 and Abaqus 2025.
