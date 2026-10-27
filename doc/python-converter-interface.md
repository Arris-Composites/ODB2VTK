# Python converter interface

`Converter` exports a complete request through a small interface. It borrows an
open source, owns no ODB handle, and does not require map construction or mutable
setup calls. Source ownership is described in [the source interface](python-source-interface.md).

## Export frames and history

Run real ODB operations under Abaqus Python with the repository's `python`
directory on the import path:

```python
from odb2vtk_core import AbaqusSource, Converter, OutputOptions, Selection

selection = Selection(["PART-1-1"], {"Step-1": [0, 1]})
outputs = OutputOptions.from_odb(odb_path, suffix="_case")

with AbaqusSource.open(odb_path) as source:
    converter = Converter(source)
    metadata = converter.inspect()
    frames = converter.export_frames(selection, outputs)
    history = converter.export_history(selection, outputs)
```

`export_frames` validates the whole selection, builds a mesh snapshot and indices
once for that operation, streams each selected frame, and creates the collection
after all requested frames succeed. A subsequent export builds its own mesh state;
changing selection cannot reuse stale indices. Geometry reuse follows the source
contract: `mesh(instance)` describes a stable mesh without a frame argument.

History export validates its selected steps and does not construct a mesh. It
preserves the existing schema, exports all history regions in those steps, and
does not filter history samples by the selected frame indices or instance names.
For a history-only operation, instances and frame lists may be empty:

```python
selection = Selection([], {"Step-1": []})
history = converter.export_history(selection, outputs)
```

`inspect()` returns the existing instances/steps/frame-label JSON structure
without writing files. `export_header(outputs)` publishes that structure as JSON.

## Selection and output options

`Selection(instances, steps)` copies its inputs into immutable tuples. Steps may
be a mapping or an ordered sequence of `(step_name, frame_indices)` pairs. Order
is preserved. Names must be nonempty strings and indices must be nonnegative
integers. Duplicate instances, steps, or frame indices are rejected.

Frame export requires nonempty instances and frames. Both frame and history
exports reject unknown instance/step names and out-of-range supplied indices
before mesh conversion or file creation.

`OutputOptions(directory, name, suffix="", write_pvd=True)` owns the naming policy.
`directory` is the parent directory; the data folder is `name + suffix`:

```text
directory/
  job_case.json
  job_case/
    Step-1_0.vtu
    Step-1_1.vtu
    job_case.pvd
    job_case.csv
```

`OutputOptions.from_odb(path, suffix="")` derives the parent and base name using
the existing first-dot filename policy. Explicit `OutputOptions` lets callers
choose a different parent and base name. Paths are normalized to absolute paths.
Names/suffixes cannot introduce path separators or invalid portable filename
characters. Existing path conflicts and destination collisions are rejected
before mesh conversion. Filesystem errors can still occur during publication.

Set `write_pvd=False` to export VTU frames without a collection. This flag has no
effect on CSV or JSON export. There is no implicit history export during frame
export; each operation returns its own result.

## Results, errors, and publication

Successful operations return `ExportResult(paths, frames, diagnostics)`:

- `paths` contains only final files successfully published by that operation.
- `frames` contains `FrameExport(step, frame, timestep, path)` records for
  completed VTU files, in requested order.
- `diagnostics` contains actual omitted-field reports, such as an unsupported
  position. This reports existing omissions without adding position support.

Handle failures through `odb2vtk_core.errors`:

| Error | Meaning |
| --- | --- |
| `SelectionError` | Malformed selection, missing name, or invalid frame index |
| `OutputError` | Invalid options, conflicting destinations, or publication failure |
| `SourceError` | Closed source, unreadable metadata, or inconsistent mesh data |
| `ExportFailure` | An export operation failed; `result` records completed files and `cause` retains the error |

Validation errors are raised before conversion. Errors during an operation are
wrapped in `ExportFailure`, including source/serialization errors, publication
errors, and errors raised by a progress callback. Callers can inspect partial
completion without guessing from filenames:

```python
from odb2vtk_core.errors import ExportFailure

try:
    result = converter.export_frames(selection, outputs)
except ExportFailure as error:
    completed_paths = error.result.paths
    underlying_error = error.cause
    raise
```

Each file is written to a unique temporary sibling, closed, and replaced into its
final path. Failed serialization preserves the previous destination and removes
the temporary file. Final paths enter the result only after replacement succeeds.

Publication is atomic per file, not across the entire request. Completed files
remain if a later frame fails. An existing collection is left untouched on frame
failure; a new collection is published only after all requested frames finish.
There is no rollback of files already completed. A collection-publication failure
therefore reports completed VTUs without claiming a completed PVD.

`KeyboardInterrupt` and `SystemExit` propagate normally; temporary-output cleanup
still runs. Source closure remains the responsibility of its owning context.

## Progress and memory

Pass an optional `progress` callback to `Converter(source, progress=callback)`.
It receives immutable `ProgressEvent(kind, path, completed, total)` records after
successful publication. Event kinds are `frame_completed`, `collection_completed`,
`history_completed`, and `header_completed`. The library prints nothing by default.

The writer receives field metadata separately from lazy numerical field iterators.
It writes each field before requesting the next one. Memory holds the selected
mesh, current numerical processing data, and output/diagnostic metadata, rather
than retaining all normalized arrays. The source's current-frame native handle
cache may retain SDK buffers until frame eviction or closure; see the
[cache measurements](python-source-cache-optimization.md). History export assembles its selected table
in memory. See [Phase 5 results](python-phase5-results.md) for measured frame-export
duration and memory on real and generated ODBs.

## Package entry points

The old `ODB2VTK` and `ReadableOdb` interfaces and standalone Python scripts
have been removed. Import the four public exports from `odb2vtk_core` for
library use. From the repository's `python` directory, run
`abaqus python -m odb2vtk_core` for direct conversion or
`python -m odb2vtk_core.parallel` for the host runner. See the
[migration guide](python-architecture.md#interface-migration).

PVD-only export now uses `export_collection(selection, outputs)`, which requires
all referenced VTUs to exist. `validate_frames`, `validate_history`, and
`validate_collection` support preflight checks without numerical conversion or
file creation; normal export methods still validate their own requests.

The [CLI and parallel runner](python-cli.md) share argument validation. The runner
verifies frame-worker receipts and output files before scheduling the collection.
