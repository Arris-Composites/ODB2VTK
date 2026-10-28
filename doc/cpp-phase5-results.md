# C++ Phase 5: final parity and performance

Completed on 2026-10-27, following Phase 4 commit `4acbc7e`. The Python reference
remains `0fe548c`; Python production code is unchanged. The five planned serial
alignment phases are complete. Native parallel coordination remains a separate
follow-up, not part of this parity claim.

## Final correctness gate

The final build passed seven native CTest suites and five SDK-independent suites.
These include 18 element-family checks, 62 numerical/source checks, 123 writer/
publication checks, 103 CLI/execution checks and exclusive-profile accounting.
The final two-step CLI run also passed 48 actual process cases, including status,
preflight, collection-only and locked-file failure checks. Phase 4 separately
records the broader 192-process matrix.

| Fixture | Selected frames per format | Native VTUs, both formats | Coverage |
| --- | ---: | ---: | --- |
| Job-1 | 2 | 4 | Real geometry, stress, orientations and history |
| Planar | 2 | 4 | Real planar geometry and fields |
| Mixed | 2 | 4 | Sections, overlapping instance labels, mixed IP counts |
| No stress | 2 | 4 | Missing stress/orientation, B/A instance order |
| Double precision | 1 | 2 | Native double field data |
| Compact labels | 4 | 8 | 160,000 nodes, 20,000 C3D8R cells |
| Sparse labels | 4 | 8 | Same size, label stride 11 |
| Two steps | 4 | 8 | Step-2:1,0 then Step-1:0,1, B/A order |

All **42 native VTUs and 284 field arrays** match the corresponding Python format
exactly when decoded. Geometry, topology, numeric types, names, component labels
and active metadata match, with no VTK warning/error events or rounding
differences on these ODBs. JSON, CSV and PVD match as well. Binary offsets,
UInt64 lengths and complete payload extents are independently checked. All
original/input-copy hashes remain unchanged.

Empty arrays, Unicode/control escaping, special floats and Float32 midpoints
also pass the edge checks. The shared VTK ASCII `-inf` reader limitation and
two intentional one-ULP midpoint examples remain explicitly recorded in
[Phase 3](cpp-phase3-results.md); binary preserves the original special values.
They are not hidden inside a broad numerical tolerance.

## Measured optimization

The initial native scaling probe put 89% of workflow time in ASCII serialization.
The optimization replaces per-number iostream formatting with C++17 `to_chars`
and a fixed 64 KiB numerical text buffer. It preserves 17-digit floating-point
round trips and exact Int64 decimal topology, with bounded writes and one
assembled field at a time. Binary encoding and field assembly are unchanged.

Every benchmark VTU is **byte-identical to its saved pre-optimization C++
counterpart**, including ASCII. The speedup does not come from reduced precision
or fewer exported values. The old formatter is not retained as a runtime branch;
a source-restoration patch exists only for reproducing the validation baseline.

Median C++ ASCII workflow seconds, from three fresh processes per cell:

| Fixture | Stream baseline | Optimized | Speedup |
| --- | ---: | ---: | ---: |
| Job-1 | 0.167 | 0.066 | 2.54x |
| Compact | 5.137 | 0.928 | 5.54x |
| Sparse | 5.144 | 0.958 | 5.37x |

Binary controls remain similar before/after, within run variability. No change
to dense/sparse label tables was justified: native mesh preparation is roughly
54–64 ms in the final large-fixture probes, a small part of total workflow time.

## Python/C++ timing

Measured on an Intel Core i5-13400F (10 cores/16 logical processors), 31.8 GiB
reported physical memory, Windows x64 Release, MSVC 19.41, Abaqus 2025 HF1,
Python 3.10.5/NumPy 1.22.4 and VTK 9.7.1.

Both implementations opened the same ODB path/bytes. Each implementation/format
had one discarded warmup and three alternating fresh-process measurements.
Separate instrumented probes followed those measurements: 54 primary processes,
18 warmups and 18 phase probes across three fixtures, including the saved native
baseline. Timings include history, frames, PVD and source closure.

Median workflow seconds:

| Fixture | Format | Python | C++ | Python/C++ ratio |
| --- | --- | ---: | ---: | ---: |
| Job-1 | ASCII | 0.295 | 0.066 | 4.49x |
| Job-1 | Binary | 0.184 | 0.058 | 3.16x |
| Compact | ASCII | 5.996 | 0.928 | 6.46x |
| Compact | Binary | 2.212 | 0.575 | 3.85x |
| Sparse | ASCII | 6.301 | 0.958 | 6.57x |
| Sparse | Binary | 2.483 | 0.604 | 4.11x |

Python package/SDK imports precede its workflow timer; native API initialization
is included in `odb_open`. Process-wall measurements include launch, loading/
imports, reporting and shutdown. For the compact fixture, median process-wall
time is 6.442/1.003 seconds for Python/C++ ASCII and 2.647/0.640 for binary.
The raw report preserves all wall times, outside-workflow times and sample ranges.

These are warm-cache, buffered-write measurements, without `fsync`. They do not
predict cold disk, network storage or every production ODB. Three samples expose
variability rather than establish a broad statistical guarantee: sparse Python
ASCII, for example, ranges from 6.297 to 7.772 seconds despite a 6.301 median.

## Exclusive native phases

One separate compact-fixture probe, in milliseconds. Nested source callbacks
and assembly scopes are subtracted from their parents, so columns add to the
measured workflow without double counting. These are probes, not sample medians.

| Phase | Baseline ASCII | Optimized ASCII | Binary |
| --- | ---: | ---: | ---: |
| ODB open/API initialization | 10.86 | 10.74 | 10.76 |
| Validation | 10.32 | 10.30 | 10.23 |
| Mesh preparation | 52.19 | 53.85 | 54.40 |
| Field discovery | 148.24 | 153.65 | 158.41 |
| Field read/copy | 121.50 | 119.02 | 120.03 |
| Field assembly | 121.14 | 125.34 | 119.70 |
| VTU serialization | 4,585.35 | 407.77 | 66.07 |
| File publication | 23.63 | 22.95 | 35.55 |
| History | 0.14 | 0.14 | 0.14 |
| Collection | 0.04 | 0.04 | 0.04 |
| ODB close | 12.72 | 12.64 | 12.80 |
| Orchestration | 12.22 | 12.00 | 10.57 |

Profiling is internal validation instrumentation. Without an installed session,
scopes read no clocks and record nothing. The existing source/writer interfaces
and normal CLI flags remain unchanged. The raw report includes corresponding
Python probes and sparse-fixture probes.

## Memory, files and reader cost

Median process peak working set includes each runtime and SDK. Output totals
include VTUs, CSV and PVD; header inspection is checked outside the timed workflow.
Reader times sum all selected frames after correctness reads, using three
alternating warm VTK reads and excluding VTK/Python imports.

| Fixture | Format | Python peak MiB | C++ peak MiB | C++ output MiB | C++ warm read seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| Job-1 | ASCII | 105.7 | 52.5 | 2.49 | 0.110 |
| Job-1 | Binary | 105.4 | 52.4 | 1.29 | 0.002 |
| Compact | ASCII | 150.3 | 119.0 | 86.98 | 3.903 |
| Compact | Binary | 149.6 | 119.0 | 49.75 | 0.043 |
| Sparse | ASCII | 152.3 | 119.7 | 84.95 | 3.891 |
| Sparse | Binary | 151.3 | 119.7 | 49.75 | 0.043 |

Binary therefore retains a substantial reader/file-size benefit even after
native ASCII generation becomes much faster. ASCII output sizes differ between
Python and C++ due to textual number formatting; decoded values match exactly.

## Artifacts and limits

- [Parity, test matrix and code hashes](validation/cpp-phase5-results.json)
- [Full samples, phase probes, memory, sizes and reader timings](validation/cpp-phase5-benchmark.json)
- [Reproduction commands and baseline procedure](cpp-performance.md)

The obsolete native adapter was removed in Phase 4; no old converter/writer path
remains in the executable. Historical phase reports retain their original audit
findings. Current build and CLI instructions describe only the maintained path.
Other SDK versions/platforms, Debug builds, every cell/field combination and
native parallel coordination are outside the validated matrix.
