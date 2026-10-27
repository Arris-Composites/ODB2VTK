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
installing NumPy alone. The host of `python -m odb2vtk_core.parallel` needs Python 3.10–3.12 but
does not need NumPy; workers run in Abaqus Python. VTK is optional validation
tooling and is never imported by the converter.

## Interface migration

The old Python interface has been abandoned. `python/odb2vtk.py`,
`python/multiprocess.py`, `python/utilities.py`, `odb2vtk_core/legacy.py`, and
`source.ReadableOdb` have been removed. No aliases or deprecation wrappers remain.
The original five-phase work kept compatibility temporarily; that requirement
was explicitly retired after Phase 5.

| Former use | Supported replacement |
| --- | --- |
| `abaqus python odb2vtk.py ...` | `abaqus python -m odb2vtk_core ...` |
| `python multiprocess.py ...` | `python -m odb2vtk_core.parallel ...` |
| `ODB2VTK(path, suffix)` | Open `AbaqusSource` in a context, then construct `Converter(source)` |
| `ReadArgs` / `ConstructMap` | Create immutable `Selection` and `OutputOptions`; pass them directly to an export operation |
| `ExtractHeader` | `export_header(outputs)` |
| `WriteVTUFiles` / `WriteVTUFile` | `export_frames(selection, outputs)`; select one frame for a single-file request |
| `WritePVDFile` | `export_collection(selection, outputs)` for existing VTUs, or use `write_pvd=True` during frame export |
| `WriteCSVFILE` | `export_history(selection, outputs)` |
| `ReadableOdb` native getters | Normalized `AbaqusSource` reads documented in the source guide |
| `GetExportFileName` | `OutputOptions` destination properties and `frame_path` |

Run module commands from the repository's `python` directory, or add that
directory to `PYTHONPATH`. Command options, output naming, and file formats are
unchanged by this interface removal. The converter borrows its source: it does
not close it or act as a context manager. Source contexts own resource cleanup.

Raw field/bulk helpers and mapping functions from the former interface also
remain removed. Numerical helpers in `mesh.py` and `fields.py` are internal
plain-data functions, not replacements for raw native-object access.

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

The generator refuses to overwrite an existing ODB. Run each benchmark sample
in a fresh process with identical database/frame selections and compare medians.
The current benchmark accepts complete requests using only the new interface.
Timing excludes imports/SDK startup and includes opening, mesh preparation,
frame writing, and closure. Peak RSS includes interpreter/SDK memory and native
allocations, not just NumPy arrays. The historical baseline comparison tooling
and old interface are available in commit `8f0d58e`; the recorded Phase 5 samples
refer to that snapshot, not to a compatibility mode in the current package.

See [Phase 5 results](python-phase5-results.md) for the recorded comparisons,
performance tradeoffs, and remaining validation limits.
