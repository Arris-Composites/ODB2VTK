# ASCII write batching

Implemented and measured on 2026-10-26 using Abaqus 2025 HF1, Windows x64,
Python 3.10.5 and bundled NumPy 1.22.4. The original
[phase profile](python-profiling-results.md) identified VTU serialization as the
largest cost. This change batches formatted text before passing it to the stream.

## Change

`writers.py` now submits up to **4,096 rows per write** for coordinates, field
arrays, connectivity, offsets, and cell types. The same numeric conversion,
spaces, newlines, array order, XML metadata, and default stream encoding are
retained. No public tuning option or new runtime dependency is introduced.

The helper consumes rows lazily and buffers a bounded chunk rather than a whole
field or VTU. Extra text memory scales with chunk row count and formatted row
width. A field with many integration-point components can therefore require
more temporary text memory than the six-component arrays in this benchmark.

## Chunk-size experiment

Three fresh Abaqus processes per variant and fixture, in rotated sequential
order. Each run opened the ODB, exported the selected frames and a PVD, then
closed the source. The bundled fixtures also exported history. Imports, SDK
startup, cProfile, and detailed phase instrumentation were excluded from these
workflow timings. OS file caches were not cleared.

Only the writer differed: the saved writer from commit `67cb637` was compared
with the current writer using each candidate chunk size. Medians in seconds:

| Fixture | Original | 256 rows | 1,024 rows | 4,096 rows | Reduction with 4,096 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Job-1, 2 frames | 0.471561 | 0.426629 | 0.415667 | **0.415014** | 12.0% |
| 2D planar, 2 frames | 0.120040 | 0.121419 | 0.115754 | **0.114997** | 4.2% |
| Generated, 4 frames | 7.884110 | 6.518258 | 6.492079 | **6.415500** | 18.6% |

The generated ODB has 80,000 nodes, 10,000 C3D8R cells, U/RF, four nodal scalars,
and stress. The final exports total 52,551,564 bytes. The 4,096-row setting had
the lowest median on all three fixtures, so it was selected as the internal
default. Differences between candidate chunk sizes are small and overlapping
samples do not establish a universal optimum. The planar improvement is about
5 ms and should be treated cautiously; native ODB cleanup dominates that case.

Peak process working-set medians, including interpreter and SDK memory:

| Fixture | Original MiB | 4,096 rows MiB |
| --- | ---: | ---: |
| Job-1 | 105.36 | 104.93 |
| 2D planar | 104.34 | 104.22 |
| Generated | 127.20 | 127.52 |

The generated case increased by about 0.32 MiB (0.25%). These are process-level
observations, not exact buffer allocation measurements. They show no material
memory regression on these fixtures; they do not measure every possible row
width or multi-gigabyte production model.

## Why it helps

A separate function profile counted **982 text writes**, compared with
**2,760,282** in the original scaling profile for the same four-frame workload.
That is a 99.96% reduction in calls. Larger strings are also encoded fewer times.
The stream was already buffered; this change reduces Python/encoding overhead
and is not a claim that each original call performed a disk syscall.

A separate pair of phase probes measured VTU serialization at **5.159 seconds
before** and **3.591 seconds after**. Mesh preparation, field discovery, reads,
and numerical assembly remained close to their prior values. Those are single
instrumented probes, separate from the three-sample workflow medians above.
cProfile runtimes also include tracing overhead and are not used for the speedup.

Every number still needs formatting, and SDK/mesh work still runs. Consequently,
the reduction in write calls produces an 18.6% workflow reduction rather than a
similar reduction in total runtime. Serialization remains the largest phase.

## Correctness checks

- Every candidate's final VTU/PVD/history output set matched the original writer
  byte-for-byte on all three fixtures.
- All **eight baseline/chunked VTU pairs** loaded successfully through VTK.
  Coordinates and every point/cell array matched after reader conversion.
- The suite now contains **107 tests**, all exercised across the available
  environments: 104 passed/3 optional skips under ordinary Python, 105 passed/2
  VTK skips under Abaqus with a real ODB, and 106 passed/1 native-source skip in
  the optional VTK environment.
- New tests cover empty input, complete/partial chunk boundaries, signed zero,
  very small/large numbers, infinity/NaN text, and writing before an entire large
  field has been consumed. Existing tests continue to cover streaming and atomic
  publication failures.

The [recorded runs, hashes, phase probes, and write counts](validation/python-write-chunk-benchmark.json)
preserve the measurements. Temporary ODBs, full exports, saved baseline writer,
and raw function profiles remain outside the repository.

## Reproduce

Use the normal `profile_exports.py` tool for the selected default. To reproduce
the chunk-size experiment, save `python/odb2vtk_core/writers.py` from commit
`67cb637` as a UTF-8 Python file. For example, from PowerShell at the repo root:

```powershell
git show 67cb637:python/odb2vtk_core/writers.py | Set-Content -Encoding UTF8 C:/temp/baseline_writers.py
```

With the generated fixture and a writable report directory, run each sample in
a fresh process:

```text
abaqus python python/validation/benchmark_write_chunks.py --baseline-writer C:/temp/baseline_writers.py --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _original --report C:/temp/original.json --no-phases
abaqus python python/validation/benchmark_write_chunks.py --chunk-rows 4096 --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _chunked --report C:/temp/chunked.json --no-phases
```

Repeat with 256 and 1,024 rows, rotate variant order, and compare medians. The
validation wrapper replaces only the VTU writer for its process; it does not
restore any removed converter interface or add production configuration.
