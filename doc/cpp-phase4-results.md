# C++ Phase 4: CLI and execution

Completed on 2026-10-27, following Phase 3 commit `c4750f0`. Python reference
`0fe548c` remains unchanged. The serial executable now calls the maintained
export interface directly. The obsolete `odb2vtk.cpp`/`odb2vtk.h` CLI adapter is
removed because it has no remaining callers.

## Behavior

The SDK-independent parser constructs a complete request before source creation.
It validates required flags/values, existing input files, format/boolean choices,
portable output names, duplicates and strict explicit frame lists. Argument,
selection and help paths no longer access unchecked empty argument vectors.
Windows receives wide arguments and converts them to UTF-8 internally.

All serial flags are present: header, input, instances, steps, suffix, history,
collection-only and ASCII/binary selection. CLI defaults match Python: ASCII,
empty suffix, no history and no automatic collection. `--writePVD 1` indexes
existing files; it does not convert frames. Step, frame and instance order are
preserved. Header mode does not require a data selection.

The native parser intentionally rejects repeated flags and abbreviated names,
following the alignment plan. Python argparse still permits some such forms.
No new parallel scheduler or worker receipt protocol was added.

Execution preflights both the data request and optional history destination
before publishing either. The factory-created source is explicitly closed and
destroyed before successful return. Failure cleanup preserves the original
error when closing also fails. Prior operation receipts are merged with partial
frame receipts, so later failures retain history and completed-frame paths.

Exit statuses are 0 for success, 2 for arguments/selections and 1 for runtime
failures. Errors and partial-output lists go to stderr. The CLI reference and
examples are in [cpp-cli.md](cpp-cli.md).

## Validation

Windows x64 Release, MSVC 19.41, Abaqus 2025 HF1 and VTK 9.7.1.

| Check | Result |
| --- | --- |
| SDK-independent CTest | Four suites pass, including 103 CLI/execution checks |
| Native CTest | Six suites pass |
| Actual CLI processes | 192 cases pass across Job-1, planar, no-stress and generated two-step fixtures |
| File parity | 20 native VTUs match corresponding Python output in both formats; JSON/CSV/PVD and active metadata match |
| Ordering | Reversed frames and two-step order verified through native processes; B/A instance order matches Python |
| Collection-only | VTU SHA-256 and modification times unchanged |
| Defaults | ASCII only, no CSV/PVD unless requested |
| Input safety | All original ODBs and implementation-specific copies retain their hashes |
| Failure paths | Invalid args/selections, corrupt ODB, missing collection references, output conflicts and locked second frame have expected statuses |
| Closure/receipts | Source, progress, history and close failures checked through the injected source interface |

Each fixture runs 48 process cases: matching Python/C++ cases plus native-only
checks for the two deliberately stricter argument rules. Python runs in Abaqus
and records its actual public CLI return value rather than trusting the launcher's
exit status. The harness preserves Unicode arguments through JSON after observing
the Abaqus Windows batch launcher map Greek mu to the micro sign. Native arguments
are passed directly to the executable. Python production code is unchanged.

The publication failure test locks the second frame destination on Windows.
Both implementations return 1, retain that old frame, leave the first completed
frame available and report its path plus the already-published CSV. No temporary
output files remain after the checked failures. Output conflicts and missing
collection references fail before optional history is created.

See [machine-readable results](validation/cpp-phase4-results.json). The shared
VTK ASCII special-value limitation recorded in [Phase 3](cpp-phase3-results.md)
still applies. Other platforms/SDK versions and native parallel coordination
remain unverified. Phase 5 adds the final integration/performance report; no
speed claim is made here.
