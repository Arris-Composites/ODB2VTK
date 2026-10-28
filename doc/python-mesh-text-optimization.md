# Reuse serialized mesh sections across frames

Implemented and measured on 2026-10-27, Windows x64, Abaqus 2025 HF1,
Python 3.10.5 and NumPy 1.22.4. Baseline commit `1a5afd9` includes vectorized
field label mapping and all previous optimizations.

## Cost and implementation

A preliminary four-frame generated-fixture probe measured 3.439 seconds total,
including 2.223 seconds of VTU serialization. Coordinate formatting/writing
accounted for 0.291 seconds and cell-array formatting/writing for 0.163 seconds.
Those repeated static sections therefore cost about 0.454 seconds per request.
The probe times `_write_rows` for the point matrix and `_write_lines` outside
field/coordinate row formatting for the three topology arrays; tiny XML header
costs are not included in that static subtotal.

For requests selecting more than one frame, the converter now opens one
`serialized_mesh` context after preparing the mesh. The writer renders the
`Points` and `Cells` sections once into a shared ASCII spool, recording the split
offset. Each VTU receives the same sections through bounded copies. Dynamic
point/cell fields are still streamed separately for every frame. The cache is
scoped to this export and discarded before publishing the PVD; a subsequent
request always builds a new cache. There is no cache on the source or converter.

The spool holds up to 1 MiB before spilling to a system temporary file. Copy
chunks are at most 64 KiB of ASCII text. Formatting chunks can temporarily cross
the spool limit before rollover, so 1 MiB is a rollover threshold, not a strict
process memory cap. The context closes storage on success, rendering failure,
spill failure, output failure or progress callback failure.

Single-frame requests bypass storage entirely and use the original direct
formatting path. The mesh is already fixed for an export by the existing
converter workflow. The writer checks that an optional cache belongs to the
same mesh object; direct callers must keep that snapshot unchanged while reusing
it. Existing `write_vtu` calls remain valid. There are no command or source
interface changes and no new output format.

ASCII storage uses untranslated `\n` internally, so offsets are both byte and
character counts. Copying through the destination text stream preserves its
newline policy, including Windows CRLF, without doubling line endings.

## Complete-export benchmark

Five fresh Abaqus processes per variant and fixture, alternating baseline and
current packages sequentially. Both variants use identical ODB bytes, instances,
frame selections and PVD; bundled fixtures also export history. Imports/SDK
startup and detailed instrumentation are excluded. Cache creation, rollover,
copying and closure are included. OS caches were not cleared.

Median complete-workflow times:

| Selection | Repeated formatting, seconds | Cached, seconds | Less time |
| --- | ---: | ---: | ---: |
| Job-1, 2 frames | 0.311926 | 0.305442 | 2.1% |
| 2D planar, 2 frames | 0.097556 | 0.098639 | -1.1% |
| Generated compact, 4 frames | 3.370465 | 3.070538 | **8.9%** |
| Generated sparse, 4 frames | 3.453635 | 3.204434 | **7.2%** |
| Generated compact, 1 frame | 1.533136 | 1.532662 | 0.03%; effectively unchanged |

Generated fixtures contain 80,000 nodes and 10,000 C3D8R cells, with nodal
scalar/vector fields and integration-point stress. Sparse labels use stride 10.
Compact four-frame samples ranged from 3.344–3.442 seconds before and
3.052–3.087 after. Sparse samples ranged from 3.441–3.498 before and 3.146–3.218
after. Small and single-frame differences are close to sample variation;
the tiny planar case has a small measured overhead. These synthetic cases do
not establish performance for every production ODB or element family.

| Selection | Repeated peak MiB | Cached peak MiB |
| --- | ---: | ---: |
| Job-1, 2 frames | 104.56 | 105.08 |
| 2D planar, 2 frames | 104.32 | 104.33 |
| Generated compact, 4 frames | 122.66 | 122.78 |
| Generated sparse, 4 frames | 123.32 | 123.72 |
| Generated compact, 1 frame | 111.51 | 111.65 |

Peak process memory includes interpreter and native SDK allocations. Increases
in the median measured peaks were below 0.6 MiB for these selections; this is
not a universal bound on peak memory. The generated mesh text exceeds 1 MiB and
exercises disk rollover.

Separate phase probes measured VTU serialization at 2.392 → 1.971 seconds for
compact labels and 2.170 → 1.914 seconds for sparse labels, including cache
preparation and cleanup. The compact baseline probe also had an unrelated slow
ODB close (0.370 seconds versus 0.063 after), so its total-time difference must
not be attributed entirely to this optimization. The 50 uninstrumented primary
samples above are the performance comparison.

## Validation

All final VTU/PVD/history output sets matched byte-for-byte across the five
selections. Input ODB hashes were unchanged. All **13 baseline/current VTU pairs**
loaded through VTK without error or warning events and had identical coordinates
and point/cell arrays.

The suite discovers **140 tests**. Ordinary Python passes 136 with 4 optional
skips; Abaqus with a real ODB passes 138 with 2 VTK skips; the VTK environment
passes 138 with 2 native-source skips. New tests cover memory/disk cache paths,
empty geometry, special numeric values, changing frame fields, CRLF translation,
snapshot identity, single-frame bypass, request-scoped reuse, spill/render/write
failures, storage closure and preservation of existing atomic destinations.

The [recorded samples, probes and hashes](validation/python-mesh-text-benchmark.json)
retain the measurements. Fixtures and generated exports remain outside the repo.

## Reproduction

Check out `1a5afd9` separately and pass its `python` directory as the baseline.
Use fresh processes with alternating variants and compare medians:

```text
abaqus python python/validation/benchmark_mesh_text.py --baseline-python-dir C:/temp/old/python --variant repeated --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _repeated --report C:/temp/repeated.json --no-phases
abaqus python python/validation/benchmark_mesh_text.py --baseline-python-dir C:/temp/old/python --variant cached --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _cached --report C:/temp/cached.json --no-phases
```

Repeat with `--frames 0` to measure the single-frame path. Omit `--no-phases`
for separate phase probes. The profiler includes cache construction and closure
in VTU serialization, even though they happen outside individual frame writes.
