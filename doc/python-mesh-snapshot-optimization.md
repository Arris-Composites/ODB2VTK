# Unified mesh snapshot

Implemented and measured on 2026-10-27 with Abaqus 2025 HF1, Windows x64,
Python 3.10.5 and NumPy 1.22.4. The baseline is `ef9abee`, including row-formatting
and native frame/field caching. This measures the next mesh optimization.

## Implementation and interface migration

The source now returns one `InstanceMesh(name, node_labels, coordinates, elements)`
snapshot from `mesh(instance)`. The separate `mesh_labels()` query and
`InstanceLabels` record are removed. Custom source adapters must supply node
labels in their mesh snapshot; direct users can derive element labels from
`tuple(element.label for element in mesh.elements)`. Normal converter requests
and command options continue to use the same interface.

Each native node is visited once to read its label and coordinates. Each native
element is visited once, including its label. Coordinates are written into an
owned float64 NumPy array with shape `(node_count, 3)`, avoiding long-lived Python
coordinate tuples. Geometry assembly combines coordinate matrices directly and
returns its own array, rather than creating an intermediate list of every row.

Map construction consumes the same snapshot. Map cardinalities detect duplicate
labels without a separate uniqueness-set pass. Instance identity, coordinate
counts/dimensions, label uniqueness and connectivity validation remain enforced.
Invalid snapshots fail before any conversion output is published. Snapshots and
returned geometry remain independent of the source and each other.

An initial tuple-based snapshot trial reduced time but used about 12 MiB more
peak memory on the generated fixture. That implementation was rejected. The
final array-backed snapshot below resolves that memory increase.

## Complete-export benchmark

Five fresh Abaqus processes per variant and fixture, sequentially alternating
baseline and snapshot. Each run opens the same ODB bytes, exports the same
selected frames plus PVD, and closes the source. Bundled fixtures also export
history. Imports/SDK startup and detailed profiling are excluded from these
workflow times. A complete baseline package is used because the mesh record
and source interface changed; writer code is identical in both packages.

| Fixture | Split reads, seconds | Snapshot, seconds | Less time |
| --- | ---: | ---: | ---: |
| Job-1, 2 frames | 0.371811 | 0.320600 | **13.8%** |
| 2D planar, 2 frames | 0.099198 | 0.097211 | 2.0%; small absolute difference |
| Generated, 4 frames | 4.327823 | 3.760315 | **13.1%** |

The generated fixture contains 80,000 nodes and 10,000 C3D8R cells. Snapshot
samples ranged from 3.757 to 3.789 seconds, compared with 4.319 to 4.345 seconds
for split reads. The tiny planar samples overlap; its roughly 2 ms improvement
should not be treated as a reliable general speedup. OS caches were not cleared,
and these fixtures do not represent every production database or element family.

| Fixture | Split peak MiB | Snapshot peak MiB |
| --- | ---: | ---: |
| Job-1 | 105.16 | 105.20 |
| 2D planar | 104.28 | 104.11 |
| Generated | 129.82 | 128.57 |

The generated workload uses **1.25 MiB less** median peak process memory.
Measurements include interpreter and native SDK allocations, not just NumPy.

A separate single phase-probe pair measured mesh preparation at **1.406 seconds
before** and **0.856 seconds after**. Serialization and field work stayed close
to their previous durations. These probes explain the targeted improvement;
the five-sample complete-export medians are the primary performance result.

## Validation and reproduction

All final VTU/PVD/history output sets matched byte-for-byte across the three
fixtures. Input ODB hashes were unchanged. All eight baseline/snapshot VTU pairs
loaded through VTK with identical coordinates and point/cell arrays and no
reader error/warning events.

All **119 tests** were exercised across available environments: ordinary Python
passed 115 with 4 optional skips; Abaqus with a real ODB passed 117 with 2 VTK
skips; the optional VTK environment passed 117 with 2 native-source skips. Tests
cover single native traversals, owned snapshot coordinates, non-aliasing geometry,
empty meshes, overlapping instance labels, selection order, and rejection of
invalid names/counts, duplicate labels, bad coordinate dimensions and unknown
connectivity before publication.

The [recorded samples, phase probes and code/input hashes](validation/python-mesh-snapshot-benchmark.json)
preserve all 30 final timing samples and the rejected tuple trial summary.

To reproduce, check out `ef9abee` separately, then use its `python` directory as
the baseline package path. From the current repository root:

```text
abaqus python python/validation/benchmark_mesh_snapshot.py --baseline-python-dir C:/temp/old/python --variant split --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _split --report C:/temp/split.json --no-phases
abaqus python python/validation/benchmark_mesh_snapshot.py --baseline-python-dir C:/temp/old/python --variant snapshot --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _snapshot --report C:/temp/snapshot.json --no-phases
```

Use a writable report directory, fresh processes and alternating sample order.
The wrapper selects a complete package and verifies its location before running
the existing profiler. Temporary ODBs, exports and the baseline package snapshot
remain outside the repository.
