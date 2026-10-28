# Phase 5 results: cleanup and design verification

Historical record for commit `8f0d58e`. After Phase 5, the user explicitly
abandoned the old interface. The script shims, facade, and native compatibility
reader described here have since been removed. Use the current
[migration guide](python-architecture.md#interface-migration) and
[package commands](python-cli.md). Baseline benchmark reproduction uses the
tooling at that recorded commit, not a current compatibility mode.

Completed on 2026-10-26. The five-phase Python refactor is complete within the
[plan's scope](python-refactor-plan.md). Source lifetime, immutable requests,
plain-data conversion, streaming writers, shared CLI behavior, and worker
verification now have one implementation each.

## Final cleanup

- Removed transitional raw-field/raw-bulk methods and mapping re-exports. The
  retained `ODB2VTK` facade calls only public `Converter` operations.
- Removed the facade's prepared-mesh cache. `ConstructMap` remains a validation
  compatibility call; exports prepare their own mesh without setup-order rules.
- Removed source normalization entry points and converter options used only by
  deleted helpers. Native normalization remains private to `source.py`.
- Replaced the two remaining raw-helper tests with single-frame and reselection
  exports. Both still assert the original field ordering/regression scenarios.
- Added the [architecture/runtime/migration guide](python-architecture.md),
  optional reader tests, reproducible scaling/benchmark scripts, and CI jobs for
  Python 3.10/3.12 on Windows/Linux plus an optional VTK reader job.

The low-level helper removals intentionally change undocumented library calls.
The migration table names every removed method and its replacement. Both
executable entry points, documented options, the supported facade export calls,
and `utilities.ReadableOdb` remain available.

## Reader compatibility corrections

VTK 9.7.1 loaded the previous VTU arrays but returned no active point vector:
the `Vectors` attribute contained quoted, comma-separated names instead of an
exact array name. Phase 5 explicitly corrects that metadata, sets VTU version
`1.0`, and escapes XML attribute values. Active scalar/vector/tensor widths are
1/3/9; other arrays retain their original layouts as ordinary data arrays.

Tests cover complete converter exports, active displacement/scalar/orientation
arrays, retained stress arrays, nine-component tensor activation, special
characters in names/component labels, and PVD filename escaping. Numeric storage
types, array associations, values, component labels, CSV/JSON schemas, and PVD
times/parts are unchanged. These are isolated serialization corrections, not
new tensor conversion or history behavior.

## Test results

Final discovery contains **106 tests**. All were exercised successfully across
the available environments; optional checks skip where their dependencies are
absent:

| Environment | Passed | Skipped |
| --- | ---: | ---: |
| CPython 3.12.14, NumPy 2.3.5, no Abaqus/VTK | 103 | 3 |
| CPython 3.12.14, NumPy 2.5.4, VTK 9.7.1 | 105 | 1 native-source test |
| Abaqus 2025 HF1, Python 3.10.5, NumPy 1.22.4, real ODB enabled | 104 | 2 VTK tests |

The ordinary environments skip the opt-in native-source test; VTK tests skip
when VTK is absent. Tests use complete export requests and public source
contracts, with focused plain-data numerical/writer tests. No tests construct
the converter through `__new__`, inject its private maps, or replace native
modules in `sys.modules`. Native stand-ins and the independent in-memory source
remain confined to test fixtures.

Black formatting and `git diff --check` passed. GitHub-hosted CI has been
configured but has not been executed locally. Production native imports remain
confined to `source.py`; the fixture generator is validation tooling.

## Semantic integration results

The saved pre-refactor snapshot includes the two original correctness fixes.
It and the final exporter ran against upgraded temporary copies of the two
bundled ODBs and a generated scaling ODB. Repository ODB binaries were unchanged.

| Fixture | Nodes | Cells | Frames compared |
| --- | ---: | ---: | --- |
| `Job-1.odb` | 3,840 | 2,604 | 0, 1 |
| `2d_planar.odb` | 99 | 80 | 0, 1 |
| Generated C3D8R scaling ODB | 80,000 | 10,000 | 0, 1, 2, 3 |

All **eight VTU comparisons passed**: topology, field order, associations,
component names, storage types, and numerical arrays agreed. XML numerical
comparison used `rtol=1e-12`, `atol=1e-12`. Only the documented version/active-array
metadata corrections were allowed. Each baseline/current VTU was also read
through VTK; coordinates and all point/cell arrays matched exactly after
reader conversion, with no reader error/warning events.

For both bundled fixtures, header JSON and PVD matched semantically and CSV
matched byte-for-byte. Both final entry points were rerun with header, frame,
history, suffix, and collection modes. Direct and two-worker exports matched the
final facade's VTU/PVD/CSV/JSON results for both fixtures. Phase 4's tests continue
to cover failure receipts, paths, worker scheduling, and launcher limitations.

## Duration and memory

Benchmarks reran the saved baseline on the same machine; these are controlled
current measurements, not timings collected during Phase 0. Each case has three
fresh Abaqus processes per implementation, with alternating order. The SDK is
imported before timing in both implementations because the original imports it
eagerly and the refactor imports it lazily. Timing includes ODB open, mesh
preparation, VTU export, and closure, excluding imports and launcher startup.

The scaling ODB has four frames of U/RF, four nodal scalars, and integration-point
stress on disconnected C3D8R cells. No solver was run. Medians:

| Fixture | Baseline seconds | Current seconds | Baseline peak MiB | Current peak MiB |
| --- | ---: | ---: | ---: | ---: |
| Job-1, 2 frames | 0.573 | 0.453 | 98.16 | 101.21 |
| 2D planar, 2 frames | 0.101 | 0.114 | 96.25 | 98.89 |
| Scaling, 4 frames | 11.458 | 7.786 | 179.27 | 124.00 |

The scaling case took **32% less time** and **31% less peak memory**. Job-1 took
21% less time. The tiny planar case took about 13 ms longer (13%). A profiling
probe found near-equal frame-writing time (baseline 36 ms, current 37 ms), with
additional mesh normalization/preflight and atomic publication work. This small
absolute regression is accepted for explicit ownership, validation, and reliable
publication rather than bypassing those guarantees for tiny models. Most of the
roughly 3 MiB small-case peak increase is already present after imports, before
opening the database.

A separate one-frame scaling probe peaked at 117.15 MiB, versus the four-frame
median of 124.00 MiB. This supports the streaming design's lack of full-frame
retention, alongside tests that assert each numerical field is written before
the next is read. It is one indicative sample, not a bound on every SDK's native
caches. Peak process RSS includes interpreter/SDK memory and native allocations;
it is not a Python-only allocation metric. History-table memory still scales
with selected history samples and columns.

The [recorded samples and baseline/fixture hashes](validation/python-phase5-benchmark.json)
preserve the measurements. Scripts under `python/validation` reproduce fixture
generation and individual benchmark samples. SDK startup, OS file caching, and
very short runs limit timing precision; no performance threshold gates CI.

## Remaining limits

- Native runtime validation covers Abaqus 2025 HF1 on Windows, not Abaqus 2023,
  other SDK releases, or native Linux export. Pure-Python cross-platform CI is
  configured, not locally proven on every target.
- The generated ODB tests moderate scaling, not a multi-gigabyte production
  database, every element family, mixed/adaptive meshes, or parallel scaling.
- VTK 9.7.1 reader checks passed; a ParaView GUI session and other reader versions
  were not exercised. VTK is not a runtime dependency.
- Existing unsupported positions/families, section-description grouping,
  orientation policy, Float32 field storage, history padding, PVD time/part
  semantics, and the SDK's Windows environment-variable path expansion remain
  as documented. Their redesign is outside this refactor.

Baseline snapshots, upgraded/generated ODBs, complete exports, profiling data,
and detailed comparison runners remain in task-specific temporary directories.
No binary fixtures, optional reader packages, or benchmark environments were
added to the repository. The existing unrelated `.gitignore` edit was preserved.
