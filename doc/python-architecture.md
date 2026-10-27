# Python architecture and maintenance

The supported library interface is `AbaqusSource`, `Converter`, `Selection`, and
`OutputOptions` from `odb2vtk_core`. A caller describes a complete request;
the converter validates it, prepares the selected mesh, streams fields, and
returns completed paths. No map-building or private-state setup is required.
See the [library guide](python-converter-interface.md) for executable examples,
results, errors, and publication guarantees, and the [CLI guide](python-cli.md)
for both scripts.

## Responsibilities

| Module | Responsibility |
| --- | --- |
| `models` | Plain records and immutable selection snapshots |
| `source` | Native ODB access, owned array snapshots, resource lifetime |
| `mesh`, `fields`, `history` | Numerical transformations over records and arrays |
| `writers` | Stream serialization without source queries |
| `outputs` | Immutable destination policy and atomic file replacement |
| `converter` | Validate and execute complete export requests |
| `errors` | Selection, source, output, and partial-completion errors |
| `cli` | Shared argument handling, execution, and worker receipts |
| `parallel` | Bounded subprocess scheduling and verified aggregation |
| `legacy` | Supported historical library calls delegated to `Converter` |

Dependencies flow from the entry points through orchestration to the source and
plain-data modules. Only `source.py` imports Abaqus modules in production code.
The numerical modules and writers never receive native ODB objects. Validation
scripts under `python/validation` use the SDK directly to create fixtures.

## OOP decisions

Composition provides the useful variation: `Converter` borrows a source, while
the caller owns its lifetime. `AbaqusSource` and the independent in-memory test
adapter satisfy the same documented [source interface](python-source-interface.md).
Contract tests exercise both. This is the polymorphic seam; no base class or
inheritance hierarchy is needed to make it work.

Selection and output options copy caller input into immutable records. Prepared
mesh state belongs to one export request and is not shared between selections.
Native backing storage stays inside the source; returned arrays own their data.
Stateless numerical work remains functions, with classes reserved for resource
ownership, request invariants, and export orchestration.

The converter does not print or exit. Progress is an optional callback. Export
results identify published files, and failures carry partial results. Each file
is published atomically; a request containing several files is not transactional.

Frame export holds the selected mesh and current field processing data, not all
frames or serialized XML buffers. A frame is written before the next frame is
read. Source blocks are copied one at a time. Request/result metadata grows with
the number of selected frames and diagnostics. History export assembles its
selected history table in memory; it is not a streaming time-series interface.

## Supported and validated runtimes

| Use | Runtime | Validation |
| --- | --- | --- |
| Native ODB export | Abaqus 2025 HF1, Python 3.10.5, bundled NumPy 1.22.4, Windows x64 | Unit/source tests, real ODB comparisons, both entry points |
| Pure conversion/library tests | CPython 3.12.14, NumPy 2.3.5, Windows x64 | Unit/source tests without Abaqus |
| Optional reader validation | CPython 3.12.14, NumPy 2.5.4, VTK 9.7.1 | Complete exports and real-file reader comparisons |

The maintained Python range is 3.10 through 3.12 with NumPy. CI is configured for
3.10 and 3.12 on Linux and Windows; these hosted jobs have not been run locally.
Python 3.11 is within that range but has not been separately exercised locally.
Other NumPy releases depend on their own interpreter support; no exhaustive
NumPy version matrix is claimed. Use Abaqus's bundled NumPy for native export.

Python 2 is unsupported. The old README's Abaqus 2023 note describes the
historical release; the refactored Python exporter has not been validated with
Abaqus 2023 or its Python runtime. The ODB must be readable by the installed SDK;
upgrade a copy when required. Ordinary Python cannot open native ODB files by
installing NumPy alone. The host of `multiprocess.py` needs Python 3.10–3.12 but
does not need NumPy; workers run in Abaqus Python. VTK is optional validation
tooling and is never imported by the converter.

## Compatibility and migration

Both executable filenames and documented flags remain supported. Existing
`ODB2VTK` callers retain construction, context management, `close`, `source`,
`odb`, `ReadArgs`, `ExtractHeader`, `WriteVTUFiles`, `WriteVTUFile`,
`WritePVDFile`, `WriteCSVFILE`, and `GetExportFileName`.
`utilities.ReadableOdb` remains available for native compatibility access.

`ConstructMap` remains callable for old workflows, but now validates the request
without caching mesh state. Each export prepares its own mesh. Code that relied
on inspecting or mutating old internal maps must migrate to complete requests.

Phase 5 removes transitional implementation helpers. This is an intentional
change for undocumented low-level callers, not a claim of full compatibility
with every former method:

| Removed helper | Migration |
| --- | --- |
| `WriteFieldOutputData`, `WriteDataArray`, `WriteDataArrayWithSectionPoints`, `WriteLocalCS` | Use `Converter.export_frames`; serialization consumes plain `FieldArray` records internally |
| `WriteSortedPointData`, `WriteSortedCellData` | Use `export_frames`; pure mapping functions live in `fields.py` for internal numerical work |
| `ABAQUS_VTK_CELL_MAP` | Internal `mesh.vtk_cell_type` raises `ValueError` instead of exiting |
| `ABAQUS_VTK_FIELDOUPUTS_MAP`, `source.legacy_field_layout`, `source.legacy_field_blocks`, `source.normalize_bulk_blocks` | Use the normalized source's `describe_field` and `field_blocks`; native normalization is private |

Do not recreate calls into private converter methods. New callers should use
the four public exports; plain-data functions are implementation interfaces
covered by focused numerical tests, rather than a replacement compatibility
surface for raw Abaqus objects.

## Intentional XML corrections

VTU version is now `1.0`. Active `Scalars`, `Vectors`, and `Tensors` attributes
identify the first compatible array by its exact name. They no longer contain
a comma-separated list with embedded quotes, which VTK loaded as no active
array. Active widths are 1, 3, and 9 respectively. Abaqus stress arrays with
other widths remain available as ordinary arrays with unchanged components;
the exporter does not expand them into a new tensor layout. Two-component
vectors also remain ordinary arrays. Names, component labels, and PVD filenames
are XML-escaped, including quotes and whitespace controls.

These changes alter XML metadata and escaping, not numerical data, associations,
field names, component layouts, or numeric storage types. Legacy Float32 field
storage, history CSV schema/padding, JSON schema, PVD times/parts, and output
naming remain unchanged. Active-array selection follows source order and does
not add a new user-selectable default-field policy.

## Verification commands

From the repository root with NumPy installed:

```text
python -m unittest discover -s python/tests -v
```

For reader tests in an optional environment, install `numpy vtk` and run the
same command. The two reader tests skip when VTK is absent. Set
`ODB2VTK_TEST_ODB` to a compatible ODB and run the suite with `abaqus python`
to include the native source/lifetime check. That test skips by default.

Performance tooling is separate from tests; no wall-clock threshold gates CI:

```text
abaqus python python/validation/create_benchmark_odb.py C:/temp/scaling.odb 10000 4
abaqus python python/validation/benchmark_exports.py --odb C:/temp/scaling.odb --instance PART-1-1 --frames 0,1,2,3 --suffix _current --report C:/temp/current.json
```

The generator refuses to overwrite an existing ODB. To compare against the saved
pre-refactor implementation, add `--baseline-dir DIRECTORY` containing
`baseline_odb2vtk.py` and its original `utilities.py`. Phase 0 refers to the
snapshot after the two original correctness fixes, not to a new historical
timing measurement. Run each sample in a fresh process, alternate baseline and
current order, keep database/frame selections identical, and compare medians.
The benchmark excludes imports and SDK startup equally for both implementations;
it includes opening, mesh preparation, frame writing, and closure. Peak RSS
includes interpreter/SDK memory and native allocations, not just NumPy arrays.

See [Phase 5 results](python-phase5-results.md) for the recorded comparisons,
performance tradeoffs, and remaining validation limits.
