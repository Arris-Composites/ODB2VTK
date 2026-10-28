# Python refactor: Phase 4 results

Completed: 2026-10-26. Phase 3 was committed as `443a4b0` before this work.

## Implementation

- Extracted shared parsing and execution into `cli.py`. `odb2vtk.py` is a thin
  executable that retains lazy legacy imports and delegates to `main(argv)`.
- Extracted the parallel coordinator into `parallel.py`; `multiprocess.py` is
  its thin executable. Both parsers use the same flags, selections, and naming.
- Added predictable Python statuses: `0` success/help, `2` argument/selection
  errors, `1` runtime failure, and `130` interruption. Successful header export
  no longer exits with an error string.
- Added metadata-only converter validation and strict existing-file collection
  export. PVD-only mode remains supported but refuses missing VTUs.
- Added bounded worker scheduling with `--jobs`, complete-request preflight,
  failure propagation, queued-job cancellation, and active-worker draining.
- Moved history and collection into one aggregate stage after all frame workers
  succeed. `--writeHistory` is now honored by the runner, once per request.
- Added per-job JSON requests and completion receipts. Output files and receipt
  paths are verified; process exit `0` alone cannot establish success.
- Deferred numerical imports so the host coordinator and help work without
  NumPy/site packages. Abaqus workers retain the existing NumPy dependency.

The [CLI guide](python-cli.md) records commands, statuses, scheduling, transport,
and vendor limitations. Existing numerical output conventions remain unchanged.

## Automated checks

Ordinary Python 3.12.14:

```text
python -m unittest discover -s python/tests -q
```

Result: 102 passed; the opt-in real-ODB test was skipped.

Abaqus 2025 Python 3.10.5 with `ODB2VTK_TEST_ODB` configured:

```text
abaqus python -m unittest discover -s python/tests -q
```

Result: all 103 tests passed. The existing numerical, source, ownership,
publication, and legacy regression scenarios remain covered.

New checks exercise shared parsing, malformed/duplicate selections, boolean
flags, job counts, header behavior, statuses and errors, source closure, receipt
success/failure, source-close failure after publication, preflight, bounded jobs,
aggregate ordering, missing outputs, and masked/nonzero process statuses. Help
works from another working directory and under `python -S` for both scripts.

Black and whitespace checks passed. Hosted CI has not been
run from this session.

## Real single/parallel comparisons

The committed Phase 3 implementation was snapshotted before editing. It and both
new entry points exported frames 0 and 1 of `Step-1` from upgraded temporary
copies of `Job-1.odb` (`L-SHAPE-PART-1`) and `2d_planar.odb` (`PART-1-1`).

Single-process header, frame/history, and PVD-only modes succeeded. The host
runner used two real Abaqus workers, exported history once, and generated PVDs
after verified completion. Parallel header-only mode also succeeded.

All eight VTU comparisons matched the Phase 3 XML structure and attributes, with
numerical values matching at `rtol=1e-12`, `atol=1e-12`. CSV matched byte for byte;
JSON headers and PVD references matched semantically for both entry points and
both fixtures.

Additional real checks passed:

- ODB/code directories and suffixes containing spaces; launch from another cwd.
- Ampersands and literal percent characters in the ODB name, plus `%TEMP%` in an
  output suffix. Both direct and parallel entry points were exercised.
- A real conversion from a host interpreter started with `-S`, without access
  to NumPy/site packages; SDK workers performed the numerical work.
- A locked existing destination caused host status `1`. The old file remained
  intact, the other active frame completed, temporary files were removed, and
  no PVD was created.
- An out-of-range frame caused host status `2` during preflight, before an output
  directory was created.

Original repository ODB fixtures were preserved. All upgrades, snapshots,
comparison helpers, copied code, and generated artifacts remain in task-specific
temporary directories.

## Vendor findings and remaining scope

The installed Windows Abaqus launcher reported `0` when an isolated Python script
exited with `7`. The runner's receipt protocol detects child failure despite this
launcher behavior; a direct vendor-launcher invocation can still mask the Python
entry point's status before it reaches the shell.

The native SDK expanded a known `%PATH%` token inside a literal input ODB filename,
even though the JSON request retained the exact input string. That case failed
and was not counted as a successful path check. Native environment expansion is
unchanged; spaces, ampersands, literal unmatched percent, and output suffix tokens
were separately verified successfully.

Phase 5 remains for transitional-code review, broader runtime support, large-ODB
performance, and VTK/ParaView reader validation.
