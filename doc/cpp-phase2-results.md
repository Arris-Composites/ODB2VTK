# C++ Phase 2: source ownership and numerical conversion

Completed on 2026-10-27, following Phase 1 commit `2843baa`. Python commit
`0fe548c` remains the behavioral reference. This phase establishes numerical
parity before serialization; complete file and CLI parity remain pending.

## Implementation

The SDK-independent core now owns validated selections, mesh and field records,
double-precision matrices, checked label placement, quaternion transformations
and history assembly. `Converter::convert(selection, sink)` performs a complete
request without a sequence of setup calls. Geometry and label maps are prepared
once, and assembled fields are delivered individually to a `FrameSink`.

`Source` has native Abaqus and in-memory implementations. Core-facing headers
contain no SDK types. Returned records own their buffers; block callbacks receive
owned records synchronously and are not retained. Sink arguments are borrowed
for the duration of the call. The caller owns the source and controls closure.

Cell placement uses actual integration-point identities with the global output
width. Validation rejects duplicate and unknown labels, malformed shapes,
unsupported elements and overflowing sizes. Section grouping, missing stress,
zero orientation padding and history column/padding behavior follow Python.
Both native single and double field data are copied explicitly into doubles.

The executable now uses this core through a temporary output adapter. Python
production code is unchanged.

## Native lifetime regression

The SDK crashed when two distinct native handles opened the same physical ODB,
one was closed, and the survivor was queried. The failure reproduced without
field or history processing and while API initialization remained active.

Native sources now share a database owner per physical file. Each logical source
retains its own frame cache and closed state. Query scopes retain the database
until their SDK temporaries are destroyed; physical closure occurs after the
last owner releases it. A weak registry avoids retaining unused databases.
This supports overlapping sequential source lifetimes; it does not promise
thread-safe concurrent SDK access.

The native regression checks surviving sources, repeated closure, constructor
failure recovery, retained records after closure and closure inside a block
callback. Additional runs passed with distinct planar and modified-double ODBs.

## Validation

Windows x64 Release, Visual Studio 2022/MSVC 19.41, Abaqus 2025 HF1.

| Check | Result |
| --- | --- |
| Native CTest | All four tests passed |
| Pure numerical/source checks | 62 passed, plus 18 element-mapping checks |
| Job-1 | Two frames, 14 field arrays exactly match Python |
| Planar | Two frames, 14 field arrays exactly match Python |
| Mixed instances, section points and integration points | Two frames, 14 field arrays exactly match Python |
| No stress | Two frames, four field arrays exactly match Python |
| Geometry, topology and history | Exact on all four comparisons |
| Native double field | Two populated rows match Abaqus double values exactly; 3,838 other rows are zero |
| Input safety | SHA-256 unchanged for all four comparison inputs and the double fixture |

Comparisons use raw assembled doubles before VTU storage, without tolerances or
rounding. `cpp/validation/python_reference.py` produces the reference using the
public Python converter; `odb2vtk_source_probe` produces native core records;
`cpp/validation/compare_core.py` checks them. Generated fixtures exercise sparse
labels, overlapping instance labels, sections and mixed integration-point counts.
The native `odb2vtk_double_fixture` helper creates double data only in a new copy.

Machine-readable results are in [cpp-phase2-results.json](validation/cpp-phase2-results.json).

## Remaining work

Phase 3 replaces the temporary writer: round-trip ASCII precision, appended raw
binary, escaped metadata, JSON/CSV/PVD schemas and safe per-file publication.
The current writer still uses legacy names and text formatting. Exact core
results therefore do not imply exact decoded VTU values or full output parity.
Phase 4 aligns argument parsing, defaults, ordering, paths and exit statuses.
No performance improvement is claimed by this phase.
