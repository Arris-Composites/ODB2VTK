# Python refactor: Phase 3 results

Completed: 2026-10-26.

## Implementation

- Added `Converter` with `inspect`, `export_frames`, `export_history`, and
  `export_header` operations over a borrowed normalized source.
- Added immutable `Selection` and `OutputOptions`, explicit export results,
  completed-frame records, diagnostics, progress events, and focused exceptions.
- Moved mesh preparation inside frame export. A mesh snapshot and instance-scoped
  indices are prepared once per operation and reused across its selected frames.
  History export has no mesh dependency.
- Centralized output directories, filenames, suffixes, and per-file publication.
  Temporary siblings are replaced into final destinations only after serialization.
- Made field serialization incremental by separating lightweight metadata from
  lazy numerical iterators. Frames and numerical fields are processed in sequence.
- Moved `ODB2VTK` into `legacy.py` as a delegating compatibility facade. The existing
  executable still parses its current flags; Phase 4 will extract and improve it.

See [the converter interface](python-converter-interface.md) for usage, validation,
ownership, partial completion, progress, and compatibility contracts.

## Intentional behavior changes

Selections now copy their inputs and reject duplicates, negative/noninteger
indices, missing source names, empty frame requests, and out-of-range frames.
Known output path conflicts, invalid filename components, and colliding
destinations fail before mesh conversion or file creation. Invalid selections
raise `SelectionError` instead of leaking a dictionary `KeyError`.

New frame exports create a PVD by default after all requested frames succeed;
`write_pvd=False` disables it. The legacy VTU operation retains its existing
no-collection default. Its separate PVD-only mode still creates planned references
until parallel integration is addressed in Phase 4.

Completed files and diagnostics are returned explicitly. Unsupported field
positions are reported in results while retaining existing omission behavior.
Library code reports progress through an optional callback and prints nothing.

Publication is atomic per file. A later failure leaves already completed outputs
in place, preserves the old destination for the failing file, and does not replace
the collection. `ExportFailure.result` describes only published outputs;
`ExportFailure.cause` retains the error. The operation is not a transaction over
all files, and existing completed files are not rolled back.

Existing CSV/JSON schemas, numerical output conventions, source centroid values,
section names, relative PVD references, and ordinary script invocations are
preserved. Naming derived from ODB paths retains the existing first-dot policy.
PVD time/part semantics and XML conventions are unchanged.

## Automated validation

Ordinary Python 3.12.14 with NumPy 2.3.5:

```text
python -m unittest discover -s python/tests -q
```

Result: 74 passed, with the one opt-in real-ODB check skipped.

Abaqus 2025 Python 3.10.5 with NumPy 1.22.4 and `ODB2VTK_TEST_ODB` configured:

```text
abaqus python -m unittest discover -s python/tests -q
```

Result: all 75 tests passed.

New checks cover immutable request snapshots, invalid requests before conversion,
filename/path conflicts, per-request mesh reuse, selection changes, history-only
sources, streaming order, metadata iterators, inspection, progress, diagnostics,
and per-file failure recovery. Failure checks include source reads, serialization,
collection generation, file replacement, progress callbacks, CSV/JSON formatting,
preservation of prior files, and temporary-file cleanup.

Existing regression, source ownership, CLI lifetime, and compatibility tests
remain in the suite. Their unknown-instance expectations now use `SelectionError`.
Black and whitespace checks passed; hosted CI has not been run
from this session.

## Real ODB comparison

The committed Phase 2 implementation was snapshotted before editing. The snapshot
exported both frames of `Step-1` from upgraded temporary copies of `Job-1.odb`
(`L-SHAPE-PART-1`) and `2d_planar.odb` (`PART-1-1`). The new public converter
interface exported the same selections, with source lifetime managed by context.

All four VTU files matched in XML structure and attributes, with numerical arrays
matching at `rtol=1e-12`, `atol=1e-12`. CSV contents matched byte for byte, and JSON
metadata and PVD references matched semantically. Both new operations returned
two completed-frame records and three published frame/collection paths, with no
omission diagnostics for those fixtures. Sources were verified closed afterward.

Original repository fixtures were preserved. Baselines, upgraded fixture copies,
comparison helpers, and generated output remain in task-specific temporary
directories.

## Remaining scope

Phase 4 will extract the CLI, unify argument validation, improve messages and exit
statuses, and integrate collection generation with successful parallel workers.
Phase 5 will remove unnecessary transitional code and complete broader runtime,
large-ODB performance, and VTK/ParaView validation.
