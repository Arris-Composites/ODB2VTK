# Current-frame native handle cache

Implemented and measured on 2026-10-27 using Abaqus 2025 HF1 on Windows x64,
Python 3.10.5 and NumPy 1.22.4. The baseline is `849b071`, including the existing
chunked writes and specialized row formatting. Only the source changed in this
comparison.

## Cache and lifetime

`AbaqusSource` retains the current native frame, its lazily fetched field
repository, and field handles already requested from that frame. Repeated
queries avoid traversing the native step/frame/field repositories each time.
The source interface and converter interface remain unchanged.

- A step/frame change evicts the previous frame, field and section-point handles.
  Returning to an older frame reloads it; this is not a cache of all visited frames.
- Timestamp-only queries do not fetch the field repository.
- Every query checks that the source is open before serving a cache hit.
- Failed frame lookups leave no previous frame cached under the new request.
  Missing fields are not cached as successful results.
- Index type is part of the cache key. An integer `0` cache hit cannot bypass
  native index checks for a subsequent `0.0` request.
- Closure drops source-owned cached handles before native ODB closure, including
  when native closure raises. Repeated closure remains harmless.
- Numerical blocks are still independently copied on every read. Existing live
  iterators retain the handles they need to finish their original query while
  the source remains open, even if a later query selects another frame.

The ODB is assumed stable while this read source is open. Reopen the source
after external/native edits; there is no refresh operation in this interface.

## Paired benchmark

Five fresh Abaqus processes per implementation and fixture, in sequential
alternating order. Both sources used the current converter/writer and identical
ODB bytes and frame selections. Timings include opening, selection validation,
mesh preparation, VTU/PVD export and explicit closure; the bundled fixtures also
export history. Imports, SDK startup and detailed profiling are excluded.

Median complete-workflow times:

| Fixture | Uncached seconds | Cached seconds | Less time |
| --- | ---: | ---: | ---: |
| Job-1, 2 frames | 0.401966 | 0.368919 | **8.2%** |
| 2D planar, 2 frames | 0.116032 | 0.099643 | **14.1%** |
| Generated, 4 frames | 4.994916 | 4.318128 | **13.5%** |

The generated fixture has 80,000 nodes, 10,000 C3D8R cells, U/RF, four scalar
fields, stress and the exported orientation array. Cached samples ranged from
4.301 to 4.334 seconds; uncached samples ranged from 4.901 to 5.017 seconds.
OS file caches were not cleared. Five samples establish this local comparison,
not a production-wide distribution or a cold-storage guarantee.

An initial three-sample prototype was followed by these five-sample measurements
after the invalid-index cache-key guard was finalized. The recorded primary
results contain only the final implementation's five-sample comparison.

## Memory tradeoff

Median peak process working set, including native allocations:

| Fixture | Uncached MiB | Cached MiB |
| --- | ---: | ---: |
| Job-1 | 104.88 | 105.13 |
| 2D planar | 104.18 | 104.43 |
| Generated | 127.45 | 129.97 |

The generated case uses **2.52 MiB more peak memory**, about **2.0%**. The cache
stores native handles rather than normalized numerical arrays, but SDK backing
buffers may remain alive with those handles. Retention is limited to the
source's current frame, not one numerical field or every visited frame. Fields
with larger native storage may have a larger memory cost than these fixtures.

## Phase probe and correctness

A separate pair of single instrumented probes measured field discovery plus
field reading at **0.790 seconds uncached** and **0.173 seconds cached**. Mesh
preparation and serialization stayed close to their earlier durations. These
probes support the targeted lookup savings; the five-sample workflow medians
above are the primary performance result.

Validation passed:

- All final uncached/cached VTU/PVD/history output sets matched byte-for-byte on
  the three fixtures. Input ODB hashes were unchanged.
- All eight VTU pairs loaded through VTK with matching coordinates and point/cell
  arrays, without reader error/warning events.
- The suite contains **116 tests**, all exercised across available environments:
  ordinary Python passed 112 with 4 optional skips; Abaqus with a real ODB passed
  114 with 2 VTK skips; the VTK environment passed 114 with 2 native-source skips.
- Seven new cache tests verify native lookup counts, eviction/release when
  switching frames or steps, lazy repository access, failed lookups, integer vs
  float index handling, closure failures, and interleaved iterator reads.
- An additional native integration test reads frame 0, visits frame 1, then
  revisits frame 0 and checks its field names, labels and numerical values.

The [recorded runs, hashes and phase probes](validation/python-source-cache-benchmark.json)
preserve all 30 primary timing samples. Temporary fixtures, complete exports and
the saved uncached source remain outside the repository.

## Reproduce

Save `python/odb2vtk_core/source.py` from `849b071` as a UTF-8 Python file. From
the repository root, using a compatible ODB and writable report directory:

```text
abaqus python python/validation/benchmark_source_cache.py --baseline-source C:/temp/baseline_source.py --variant uncached --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _uncached --report C:/temp/uncached.json --no-phases
abaqus python python/validation/benchmark_source_cache.py --baseline-source C:/temp/baseline_source.py --variant cached --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _cached --report C:/temp/cached.json --no-phases
```

Use fresh processes and alternate sample order. The wrapper switches only its
own process's source class; production exposes no cache-mode option. The baseline
is the previous normalized source, not a removed legacy converter interface.
