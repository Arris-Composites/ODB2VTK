# C++ Phase 3: writers and safe publication

Completed on 2026-10-27, following Phase 2 commit `65582ae`. Python reference
`0fe548c` remains unchanged. Writer and auxiliary-file parity are established
through the maintained C++ export interface; CLI parity is Phase 4.

## Implementation

`VtuWriter` implements the existing `FrameSink` interface and borrows an output
stream. It consumes one assembled field at a time and retains no field matrices
or complete point/cell text buffers. ASCII uses classic-locale double precision
with 17 significant digits before the reader converts declared Float32 fields.
Coordinates remain Float64 and topology remains Int64.

Binary is uncompressed appended raw data, matching Python: little-endian
Float64 coordinates, Float32 fields, Int64 topology and UInt64 byte-count headers.
XML offsets include each preceding eight-byte length header. Sizes and offset
arithmetic are checked. Encoding uses a fixed 64 KiB scratch buffer and explicitly
emits little-endian bytes independently of host byte order.

Both formats share XML escaping, component labels and active-array selection:
the first matching tensor/vector/scalar with width 9/3/1 becomes active. The
mesh borrowed at `begin_frame` remains valid through `end_frame`; other inputs
are borrowed only for their synchronous calls.

`OutputOptions` validates portable leaf names and follows Python's first-dot
run-name policy, suffixes and paths. `Exporter` borrows a source and provides
complete frame, header, history and collection operations. JSON frame labels,
CSV column order/zero padding/six-decimal formatting, and PVD times/parts/relative
references match Python. CSV additionally quotes headers containing commas,
quotes or newlines; Python's current writer does not quote those headers. This
intentional escaping improvement does not change ordinary history output.

The temporary native CLI adapter now calls `Exporter`; the legacy text writer
and empty auxiliary writer methods are removed. JSON and run-directory names
therefore change to the maintained Python layout. CLI parsing and exposing
binary/history/collection modes through normal flags remain Phase 4.

## Publication and failures

Output is written to a uniquely reserved temporary sibling, flushed and closed
with errors checked, then replaced using `MoveFileExW` on Windows or rename on
POSIX. The previous destination is never deleted before replacement. Windows
replacement uses no cross-volume copy fallback. Cleanup runs on exceptions.
Publication is atomic per file; it is neither a request-wide transaction nor a
durability/fsync guarantee. The Windows implementation was exercised here;
the POSIX branch has not been executed in this environment.

The collection is published after all frames succeed. `ExportFailure` carries
completed paths/frames and the original exception. Progress runs after recording
publication, so a callback failure still reports the frame already written.
Serialization, malformed field, stream, source, progress and locked-destination
failures preserve previous files and leave no temporary files in the tests.
A failed collection replacement retains receipts for both completed frames.

## Validation

Windows x64 Release, MSVC 19.41, Abaqus 2025 HF1 and VTK 9.7.1.

| Check | Result |
| --- | --- |
| Native CTest | All five suites pass |
| SDK-independent build | All three suites pass without native support |
| Real Job-1 and planar ODBs | Two frames each, ASCII and binary, exact decoded Python parity |
| Mixed section/IP and no-stress fixtures | Two frames each, both formats, exact decoded Python parity |
| Native double fixture | One frame in both formats, exact decoded Python parity |
| JSON, CSV, PVD and active metadata | Match Python on all five ODB fixtures |
| Binary layout | Offsets, UInt64 lengths and final payload extent checked independently |
| Inputs | SHA-256 unchanged on all five ODBs |
| Edge fixtures | Empty mesh/arrays, Unicode/control escaping, special floats and Float32 midpoints checked |

The native matrix contains 18 VTU files and 108 field arrays. All match their
corresponding Python format exactly, with no reader warnings/errors or rounding
differences on these ODBs. The four additional native edge VTUs also load without
warning/error events. Binary special values round directly to Float32 exactly.

Two deliberate ASCII midpoint values differ from direct Float32 conversion by
one ULP, matching Python's ASCII writer through the same reader. More seriously,
VTK 9.7.1 reads ASCII `-inf` as positive infinity even though both Python and C++
files contain the correct signed token. The test verifies raw ASCII values and
records that shared reader limitation explicitly; binary preserves the sign.
The VTK ASCII parser first attempts stream extraction before falling back to
string parsing ([upstream implementation](https://github.com/Kitware/VTK/blob/master/IO/XMLParser/vtkXMLDataParser.cxx)).
No Python production changes or ASCII compatibility workarounds were introduced.

See [machine-readable results](validation/cpp-phase3-results.json) and the
[writer guide](cpp-writers.md) for reproducible commands. No performance claim
is made here; full integration/performance measurement remains Phase 5.
