# Uncompressed appended binary VTU

Implemented and measured on 2026-10-27, Windows x64, Abaqus 2025 HF1,
Python 3.10.5 and NumPy 1.22.4. The baseline is `1f2bcd1`, including the ASCII
mesh-text cache. ASCII remains the default; binary is an explicit output option.

## Usage and format

From the repository's `python` directory:

```text
abaqus python -m odb2vtk_core --header 0 --instance "Part-1" --step "Step-1:0,1" --odbFile ../doc/Job-1.odb --format binary
python -m odb2vtk_core.parallel --header 0 --instance "Part-1" --step "Step-1:0,1" --odbFile ../doc/Job-1.odb --format binary --jobs 2
```

Use an ODB compatible with the installed Abaqus release and instance names
reported by its header. Library callers can use
`OutputOptions.from_odb(path, vtu_format="binary")` or
`OutputOptions(directory, name, vtu_format="binary")`. `--format ascii` selects
the existing writer. Both formats keep the same VTU names and PVD references;
use different suffixes when keeping both exports. CSV/JSON/PVD remain text.

The binary writer follows the [VTK XML format specification](https://docs.vtk.org/en/v9.6.1/vtk_file_formats/vtkxml_file_format.html).
XML metadata references arrays in an appended raw byte section. Offsets start
immediately after its underscore; each offset points to an eight-byte UInt64
payload-length header followed by the array bytes. Payloads use little-endian,
C-order storage, with Float64 coordinates, Float32 fields, and Int64 connectivity,
offsets and cell types. There is no compression or base64 encoding.

Those types match the ASCII writer's declarations. Existing float64 field
assembly buffers are converted to Float32 when written; this is the precision
the ASCII files already tell VTK readers to load. Binary does not introduce a
new precision option or promise float64 field storage. Raw appended bytes may
violate generic XML syntax; use a VTK reader for the complete file. Metadata can
be inspected separately before `AppendedData`.

## Implementation and memory

`binary_writer.write_vtu` shares XML escaping, component-count and active-array
selection helpers with the ASCII writer. The converter selects the writer from
immutable output options. Sources and numerical field assembly are unchanged;
there is no VTK runtime dependency and no new inheritance hierarchy.

All offsets are calculated from mesh counts and field layout metadata before
reading numerical fields. During the payload pass, each field is read, checked
against its metadata, written and released before advancing to the next field.
The writer never collects all field values when separate metadata is supplied.
Direct callers omitting metadata may supply field lists, as with ASCII.

Numeric conversion uses row slices targeting at most 1 MiB per chunk, or one row
when a row exceeds that limit. Noncontiguous and big-endian input arrays are
converted in chunks; contiguous arrays of the correct type can be borrowed.
This limit applies per chunk, not to total process memory or all live buffers.
Geometry is written directly for every frame, bypassing ASCII mesh-text storage.

Atomic publication opens binary VTU streams in `wb` mode, preventing Windows
newline translation from changing payload bytes. Failures remove incomplete
temporary files, preserve existing destinations and retain completed-frame
receipts. The format option survives parallel worker serialization, preflight,
frame jobs and collection publication.

## Conversion and reader benchmark

Five fresh Abaqus processes per format and selection, sequentially alternating
ASCII and binary. Both use the same ODB bytes, selected instances/frames and PVD;
bundled fixtures also export history. Complete workflow times include open,
preparation, conversion, publication and close; imports/SDK startup and detailed
instrumentation are excluded. OS caches were not cleared. Generated fixtures
contain 80,000 nodes and 10,000 C3D8R cells; sparse labels use stride 10.

Median complete-workflow seconds:

| Selection | ASCII | Binary | Less time |
| --- | ---: | ---: | ---: |
| Job-1, 2 frames plus history | 0.295715 | 0.185801 | **37.2%** |
| 2D planar, 2 frames plus history | 0.100435 | 0.092963 | 7.4% |
| Generated compact, 4 frames | 3.095998 | 1.183569 | **61.8%** |
| Generated sparse, 4 frames | 3.192620 | 1.323748 | **58.5%** |
| Generated compact, 1 frame | 1.550025 | 0.988984 | **36.2%** |

Compact four-frame samples ranged from 3.081–3.122 seconds for ASCII and
1.171–1.289 for binary. Sparse samples ranged from 3.176–3.280 and 1.295–1.340.
These generated cases show scaling, not every production database or cell family.
The tiny planar difference is small in absolute terms and is less informative.

| Selection | ASCII peak MiB | Binary peak MiB |
| --- | ---: | ---: |
| Job-1 | 105.27 | 105.12 |
| 2D planar | 103.99 | 104.16 |
| Generated compact, 4 frames | 123.56 | 123.01 |
| Generated sparse, 4 frames | 124.43 | 123.74 |
| Generated compact, 1 frame | 112.27 | 112.25 |

Peak process memory includes interpreter, native SDK and NumPy allocations.
There is no material increase on these fixtures. Separate phase probes measured
serialization at **1.888 → 0.014 seconds** for compact labels and
**1.914 → 0.015 seconds** for sparse labels. Binary shifts the dominant cost to
mesh preparation (roughly 67–74% in these probes). Primary performance claims use
the 50 uninstrumented samples, not these single probe pairs. Writes are buffered;
no `fsync` or cold-storage guarantee is part of either implementation or timing.

VTU sizes, excluding small auxiliary files:

| Selection | ASCII MiB | Binary MiB |
| --- | ---: | ---: |
| Job-1, 2 frames | 2.75 | 1.29 |
| 2D planar, 2 frames | 0.045 | 0.030 |
| Generated compact, 4 frames | 50.12 | 24.88 |
| Generated sparse, 4 frames | 49.22 | 24.88 |
| Generated compact, 1 frame | 12.54 | 6.22 |

Five repeated warm VTK reads of the complete four-frame compact selection had
median totals **2.034 seconds for ASCII versus 0.022 seconds for binary**. Sparse
totals were **1.930 versus 0.022 seconds**. The single-frame compact selection
was 0.508 versus 0.005 seconds. This measures parsing and cached reads on this
machine, not expected throughput from cold or network storage.

## Precision and validation

All 13 ASCII/binary VTU pairs passed VTK loading with no warning/error events.
Geometry, topology, numeric types, array names, component labels and active-array
metadata match. PVD/history files are byte-identical between formats, and every
PVD reference resolves to its expected VTU. Current ASCII output sets are also
byte-identical to the saved `1f2bcd1` package across all five selections; input
ODB hashes are unchanged.

Float32 comparisons permit at most **one ULP**, with differences recorded rather
than hidden by a broad relative tolerance. Only `Material_Orientation` in Job-1
differs: 272 components in each of two frames, maximum absolute difference
`5.960464477539063e-08`. All other decoded arrays match exactly in these fixtures.

Every differing component was verified to be an exact binary midpoint between
adjacent Float32 values. For example, the original float64 midpoint is
`0.9999999701976776123046875`, whose short ASCII token is
`0.9999999701976776`. VTK parses that decimal token just below the midpoint as
`0.9999999403953552`; direct NumPy Float32 conversion rounds the exact midpoint
to `1.0`. The negative case behaves symmetrically. Binary output was additionally
checked against Float32 conversion of original float64 orientation arrays read
through the native source; those arrays match exactly. This is an intentional
consequence of avoiding decimal conversion, not a change to field storage type.

The suite discovers **156 tests**. Ordinary Python passes 149 with 7 optional
skips; Abaqus with a real ODB passes 151 with 5 VTK skips; the VTK environment
passes 154 with 2 native-source skips. New tests cover UInt64 headers and offsets
beyond 4 GiB without large allocations, payload ordering, empty arrays, special
floats, midpoint rounding, wide/noncontiguous/big-endian arrays, bounded writes,
lazy field release, metadata mismatch failures, Unicode/XML escaping, active
arrays, binary atomic failures and option propagation through workers.

Actual serial Abaqus and two-worker parallel commands exported two Job-1 frames,
history and PVD successfully. Their binary output sets match the benchmark's
binary files byte-for-byte. ParaView GUI loading was not exercised.

The [recorded samples, probes and hashes](validation/python-binary-benchmark.json)
retain the measurements. Temporary ODBs and exports remain outside the repo.

## Reproduction

From the repository root, run each sample in a fresh process, alternating formats:

```text
abaqus python python/validation/profile_exports.py --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _ascii --format ascii --report C:/temp/ascii.json --no-phases
abaqus python python/validation/profile_exports.py --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _binary --format binary --report C:/temp/binary.json --no-phases
```

Omit `--no-phases` for separate instrumented phase probes. In an ordinary Python
environment with NumPy and VTK installed, compare decoded outputs and read times:

```text
python python/validation/compare_vtu_exports.py --reference-report C:/temp/ascii.json --candidate-report C:/temp/binary.json --report C:/temp/readers.json
```

The comparison validates geometry, topology, numerical arrays and types,
component labels, active arrays, auxiliary files and PVD frame references.
Checks require exact geometry/topology and allow at most one ULP for Float32
fields, reporting each differing field and component count. Timing uses fresh
VTK readers, one initial correctness read per file, then five
alternating warm reads per format. It excludes Python/VTK imports and is not a
cold-storage benchmark. ParaView GUI loading is a separate manual check.
