# Scalar and three-component row formatting

Implemented and measured on 2026-10-26 using Abaqus 2025 HF1 on Windows x64,
Python 3.10.5 and bundled NumPy 1.22.4. The baseline is commit `530ed9d`, which
already includes the 4,096-row [ASCII batching change](python-ascii-write-optimization.md).
These results measure the additional formatting improvement, not the complete
refactor's improvement over main.

## Implementation

The writer now selects a formatter once per array:

- One component: `str(row[0]) + "\n"`.
- Three components: join a fixed tuple of three `str` conversions, then a newline.
- Other widths: retain the general generator-based row formatter.

This removes per-row generator creation and iteration for the common widths;
the scalar path also removes the unnecessary join of a single value. Every
element still uses `str` on its original NumPy scalar, preserving dtype-specific
text. Rows remain lazy, and the existing 4,096-row chunks bound text buffering.

## Separate and combined benchmarks

Three fresh processes per variant and fixture, with sequential rotated variant
order. Each run opened the ODB, exported the selected VTUs and a PVD, then closed
the source. Bundled fixtures also exported history. Imports, SDK startup, and
detailed profiling were excluded from the timing samples. All variants used the
same converter/source, ODB bytes, frame selections, chunk size, and encoding.

Median complete-workflow seconds:

| Fixture | Baseline | Scalar only | Three-component only | Both | Reduction with both |
| --- | ---: | ---: | ---: | ---: | ---: |
| Job-1, 2 frames | 0.416063 | 0.420026 | 0.402370 | **0.399453** | **4.0%** |
| 2D planar, 2 frames | 0.118262 | 0.114308 | 0.116423 | 0.117538 | 0.6%; no meaningful change |
| Generated, 4 frames | 6.402409 | 5.554487 | 5.865339 | **4.975290** | **22.3%** |

The generated fixture has 80,000 nodes, 10,000 C3D8R cells, four scalar fields,
U/RF, stress, and the exported orientation array. Scalar-only formatting reduced
its median time by **13.2%**; three-component-only formatting reduced it by
**8.4%**. Both paths were retained because each improved that workload and their
combination gave the lowest median on both the generated and real 3D models.

Scalar formatting has no useful measured benefit on Job-1; its scalar-only
difference is small compared with sample variation. The tiny planar fixture is
dominated by fixed/native costs and its samples overlap. Improvements therefore
depend on array widths and workload size; this is not a universal percentage.

Peak process working-set medians:

| Fixture | Baseline MiB | Both MiB |
| --- | ---: | ---: |
| Job-1 | 104.90 | 104.71 |
| 2D planar | 104.23 | 104.29 |
| Generated | 127.50 | 127.46 |

No material peak-memory increase was observed. These process-level values include
the interpreter/SDK and native allocations, not just formatter storage.

Separate single phase probes measured serialization at 3.847 seconds before
and 2.220 seconds after. The optimized probe spent 44% serializing VTU and 28%
preparing the mesh. These probes corroborate the targeted improvement; the
workflow medians above are the primary performance result. Three samples and
uncleared OS file caches do not establish a production performance distribution.

## Validation

- Every final variant output set matched baseline byte-for-byte on all three
  fixtures, including VTU, PVD, and history where requested.
- All eight baseline/combined VTU pairs loaded through VTK without reader
  error/warning events. Coordinates and all point/cell arrays matched exactly.
- Input ODB hashes were unchanged after the experiment.
- All **108 tests** were exercised across the available environments: ordinary
  Python passed 105 with 3 optional skips; Abaqus with a real ODB passed 106 with
  2 VTK skips; the optional VTK environment passed 107 with 1 native-source skip.
- Writer tests cover chunk boundaries for widths 1, 3, and 6, and exact text for
  float32/float64/int32/int64 arrays of widths 1, 2, 3, 6, and 48. They include
  signed zero, rounding-sensitive values, scientific notation, infinity/NaN,
  empty arrays, partial chunks, and lazy consumption.

The [recorded samples, phase probes, and code/input hashes](validation/python-row-format-benchmark.json)
preserve the experiment. Full exports, saved baseline writer, and fixture copies
remain in task-specific temporary directories.

## Reproduce

Save `python/odb2vtk_core/writers.py` from commit `530ed9d` as a UTF-8 file, then
run from the repository root with a compatible ODB and writable report directory:

```text
abaqus python python/validation/benchmark_row_formatting.py --baseline-writer C:/temp/baseline_writers.py --variant baseline --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _general --report C:/temp/general.json --no-phases
abaqus python python/validation/benchmark_row_formatting.py --baseline-writer C:/temp/baseline_writers.py --variant both --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _specialized --report C:/temp/specialized.json --no-phases
```

Use `--variant scalar` and `--variant three` to isolate each path. Repeat samples
in fresh processes and rotate their order. The wrapper configures only its own
process; the production interface exposes no formatting-mode option.
