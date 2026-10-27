# Vectorized label-to-row mapping

Measured on 2026-10-27 with Abaqus 2025 HF1, Python 3.10.5 and NumPy 1.22.4
on Windows x64. The baseline is `64630ed`, including the mesh snapshot,
current-frame handle cache and chunked ASCII writer.

## Implementation

Previously, each field block built its row indices with a Python dictionary
lookup for every label. Mesh preparation now creates one `LabelLookup` for nodes
and one for elements in each selected instance. Field and orientation blocks
map their entire label array at once and reuse these lookups across frames.

If the label span is at most four times the number of labels, an offset array
maps labels directly to global output rows. The offset permits large starting
labels without allocating entries below the minimum. Otherwise, sorted label
and row arrays use NumPy `searchsorted`. Storage scales with selected mesh size,
even when labels have large gaps. Cached arrays are read-only; returned index
arrays are independent copies.

Geometry construction still uses dictionaries for connectivity. After geometry
validation, the converter replaces those dictionaries with numerical lookups;
it does not retain both forms for the duration of the export. Lookup construction
is included in the complete-export timings below.

Instance namespaces, selected instance order, repeated labels, integration-point
component slices and missing-point padding are preserved. Unknown labels raise
`KeyError` for the first missing input label before modifying the destination
array. Input labels must be one-dimensional integer sequences representable as
signed int64; unsigned values above that range are reported as missing without
wrapping. Output row indices use NumPy `intp` and must be nonnegative.

The converter, source and command-line interfaces are unchanged. Direct users of
the numerical helpers `place_point_data` and `place_cell_data` must now pass a
`LabelLookup(mapping)` in place of a dictionary. `build_label_maps` still returns
dictionaries for mesh assembly.

## Benchmark and validation

Five fresh Abaqus processes per variant and fixture, sequentially alternating
the complete baseline and current packages. Each pair uses the same ODB bytes,
instances, frames and PVD; bundled fixtures also export history. Times include
opening, preparation, conversion and closure, excluding SDK/import startup and
detailed instrumentation. OS caches were not cleared. The generated fixtures
have 80,000 nodes, 10,000 C3D8R cells and four frames; sparse labels use stride 10.

| Fixture | Dictionary, seconds | Vectorized, seconds | Less time |
| --- | ---: | ---: | ---: |
| Job-1, 2 frames | 0.321877 | 0.311792 | 3.1% |
| 2D planar, 2 frames | 0.097634 | 0.097858 | -0.2% |
| Generated compact, 4 frames | 3.773712 | 3.381682 | **10.4%** |
| Generated sparse, 4 frames | 3.835755 | 3.476863 | **9.4%** |

These are medians of five runs. Compact generated samples ranged from
3.719–4.003 seconds before and 3.363–3.539 seconds after; sparse samples ranged
from 3.775–3.857 before and 3.457–3.505 after. Small-fixture samples overlap,
so their differences should not be treated as reliable general speedups.
Generated cases exercise scaling rather than realistic solver workloads or
every element family.

| Fixture | Dictionary peak MiB | Vectorized peak MiB |
| --- | ---: | ---: |
| Job-1 | 104.80 | 104.82 |
| 2D planar | 104.36 | 104.45 |
| Generated compact | 128.80 | 122.95 |
| Generated sparse | 129.30 | 123.38 |

Peak process memory includes the interpreter and native SDK. Median peak memory
fell by 5.85 MiB for compact labels and 5.92 MiB for sparse labels. The bounded
lookup storage replaces Python dictionaries retained throughout field export;
temporary dictionary and lookup storage overlap during preparation.

Separate instrumented probes measured field assembly at **0.435 → 0.029 seconds**
for compact labels and **0.435 → 0.142 seconds** for sparse labels. Compact mesh
preparation increased from 0.830 to 0.865 seconds; sparse preparation was close
at 0.868 versus 0.854 seconds. Serialization stayed near 2.16 seconds in both
variants. These single probe pairs explain the targeted gain; the uninstrumented
five-run medians remain the primary result.

Final VTU/PVD/history output sets matched byte-for-byte for every fixture, and
input ODB hashes were unchanged. All **12 baseline/current VTU pairs** loaded
through VTK without error or warning events and had identical coordinates and
point/cell arrays. The suite discovers **131 tests**: ordinary Python passes 127
with 4 optional skips; Abaqus with a real ODB passes 129 with 2 VTK skips; the
VTK environment passes 129 with 2 native-source skips. Added regressions cover
dense/sparse bounds, large offsets, unsigned overflow, first-missing-label order,
ownership, repeated labels, overlapping instance labels and integration points.

The [recorded samples, phase probes and code/input hashes](validation/python-label-lookup-benchmark.json)
retain the measurements. Temporary fixtures and exports are outside the repo.

To reproduce, check out `64630ed` separately and use its `python` directory as
the baseline package path. Run each sample in a fresh process, alternating variants:

```text
abaqus python python/validation/benchmark_label_lookup.py --baseline-python-dir C:/temp/old/python --variant dictionary --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _dictionary --report C:/temp/dictionary.json --no-phases
abaqus python python/validation/benchmark_label_lookup.py --baseline-python-dir C:/temp/old/python --variant vector --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _vector --report C:/temp/vector.json --no-phases
```

Generate the sparse case with:

```text
abaqus python python/validation/create_benchmark_odb.py C:/temp/sparse.odb 10000 4 10
```

Omit `--no-phases` for a separate instrumented phase probe. The wrapper verifies
which complete package was loaded; there is no production compatibility mode.
