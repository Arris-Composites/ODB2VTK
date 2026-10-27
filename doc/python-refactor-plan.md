# Python exporter refactor plan

Status: Phases 1 and 2 completed on 2026-10-26. Later phases remain planned.
See [Phase 1 results](python-phase1-results.md) and
[Phase 2 results](python-phase2-results.md) for the implementation and validation
records. Further changes to export behavior remain separate work.

## Objective

Make the Python exporter cohesive, loosely coupled, and usable through a small
interface. Isolate Abaqus access, numerical conversion, serialization, and command
line handling so each can be understood and tested independently.

Preserve the recent fixes for history-column overwrites and integration-point
assignment throughout the migration. Deliver the refactor in independently
testable changes, with the existing scripts continuing to work between phases.

## Scope and compatibility

- Refactor `python/odb2vtk.py` and `python/utilities.py`.
- Keep `python/odb2vtk.py` and `python/multiprocess.py` as executable entry points.
- Update the parallel runner where integration requires it; broader process
  management improvements are a separate work item.
- Preserve documented flags, selected-instance behavior, output names, suffixes,
  and the existing CSV and JSON schemas for ordinary supported inputs.
- Compare exported numerical values and metadata semantically. Whitespace and
  attribute ordering are not compatibility requirements.
- Preserve current CSV padding and sampling behavior. Timestamp columns and a
  new history-table schema require a separate decision.
- Keep C++ outside this refactor.
- Keep runtime dependencies limited to the standard library and NumPy.

Before choosing syntax or typing tools, establish the supported Abaqus/Python
versions. The README names Abaqus 2023, while local checks used Abaqus 2025 with
Python 3.10. Do not introduce dataclasses, protocols, or newer syntax until the
runtime requirement is settled. Simple classes and duck typing remain an option.

Behavior changes must be identified explicitly in their implementing change.
Separate mechanical extraction from fixes to invalid XML metadata, unsupported
positions, exit statuses, path handling, or missing-data policy.

## Current architectural problems

1. `ODB2VTK` owns ODB access, selection, mesh indexing, field interpretation,
   serialization, filesystem operations, and progress output.
2. Correct usage requires `ReadArgs`, `ConstructMap`, and export methods to be
   called in a particular order. Changing selection can invalidate cached maps.
3. `ReadableOdb` forwards calls but returns Abaqus objects. Abaqus-specific
   knowledge therefore spreads through the converter.
4. Positional tuples, string switches, XML buffers, and separately maintained
   metadata dictionaries encode contracts implicitly.
5. Construction opens an external resource, with no explicit source lifetime
   interface. Library logic also prints messages or terminates the process.
6. Tests must bypass construction, populate private state, and stub imports to
   exercise numerical logic without Abaqus.

## Target module layout

Use a package name that does not conflict with the existing entry-point script:

```text
python/
  odb2vtk.py                  # Existing executable; delegates to cli.main
  multiprocess.py             # Existing parallel executable
  utilities.py                # Temporary compatibility shim, if needed
  odb2vtk_core/
    __init__.py               # Small supported library interface
    models.py                 # Selection and explicit data contracts
    source.py                 # AbaqusSource and its resource lifecycle
    mesh.py                   # Mesh indexing and element mapping
    fields.py                 # Field assembly and orientation transformations
    history.py                # History-table assembly
    writers.py                # VTU/PVD, CSV, JSON serialization
    converter.py              # Export orchestration
    cli.py                    # Argument parsing, reporting, exit statuses
  tests/
    test_exports.py           # Existing regressions, migrated as seams improve
    ...                       # Tests grouped by observable responsibility
    support.py                # In-memory source and synthetic fixtures
```

Start with one serialization module. Split it by format only when independent
growth makes that useful. Avoid one class or file per existing method.

### Responsibilities and dependency direction

| Module | Owns | Must not require |
| --- | --- | --- |
| Models | Explicit records and local invariants | Abaqus, filesystem, CLI |
| Source | ODB lifetime, Abaqus queries, conversion to plain records | XML, output paths |
| Mesh/fields/history | Numerical transformations and indexing | Abaqus objects, file writing |
| Writers | Serialization and stream output | Abaqus objects, source queries |
| Converter | Validation, iteration, filenames, export bookkeeping | Argument parsing, process exit |
| CLI | Options, source creation, progress display, error reporting | Numerical algorithms, XML formatting |

The source module is the only production module importing `odbAccess` and
`abaqusConstants`. Importing models, transformations, writers, or the converter
must work in ordinary Python with NumPy installed.

### OOP approach

- Use composition: the converter receives a source and uses conversion and
  serialization modules.
- Encapsulate selection and mesh indices; callers cannot change the selection
  underneath a prepared export.
- Make the source interface polymorphic across `AbaqusSource` and an in-memory
  test adapter. Start with duck typing; add an abstract base class only if it
  improves a concrete contract.
- Keep stateless calculations as functions. Use classes for resource ownership,
  invariants, or meaningful state.
- Keep field-position dispatch explicit. Introduce strategy objects only when
  handlers need distinct state or configuration.
- Keep helpers internal. The public interface should expose export intent rather
  than individual initialization and formatting steps.

## Data contracts

Define only the records needed by the extracted code. Establish these invariants
before finalizing their constructors:

- **Selection:** copied instance names and step/frame selections; deterministic
  order; a documented duplicate policy. Validate syntax separately from source
  existence and frame bounds.
- **MeshIndex:** node and element identity includes the instance name. Output
  indices are unique and contiguous; connectivity references known nodes. Build
  this once per fixed mesh selection, subject to verification that the source
  mesh is stable across selected frames.
- **FieldBlock:** plain arrays plus instance, position, component labels, element
  or node labels, integration-point numbers, and section-point identity as
  applicable. Row labels and values have matching lengths. Keep section-point
  identity separate from its display description.
- **FieldArray:** output name, point/cell association, component names, numerical
  values, and any necessary missing-data information. Its dimensions agree with
  the selected mesh and component count.
- **HistorySeries:** step, region, output name, timestamps, and values. Retain
  timestamps internally even while preserving the existing CSV schema.
- **ExportResult:** completed paths and reported diagnostics. Record successful
  outputs so collection generation uses the actual export results.

Source-side centroid queries must retain Abaqus's existing extrapolation behavior.
Do not replace them with a numerical average during extraction. The source also
normalizes orientation representation; pure transformation code converts those
values to the existing output convention.

Document the lifetime of arrays returned from Abaqus bulk-data objects. Copy where
required to prevent arrays from outliving their backing storage. Do not eagerly
copy an entire ODB or retain data for all frames.

## Intended library interface

Illustrative usage; finalize names after extracting the first working slice:

```python
with AbaqusSource.open(odb_path) as source:
    converter = Converter(source)
    metadata = converter.inspect()
    result = converter.export_frames(selection, output_options)
    converter.export_history(selection, output_options)
```

`export_frames` validates the request, prepares mesh indices, processes selected
frames, and writes the requested collection. Callers never initialize maps or
modify converter internals. The CLI can still support the existing PVD-only mode.

The source owns and closes the ODB, including on failures. Writers can accept
streams for direct serialization tests. Library code raises meaningful exceptions;
the CLI translates them into messages and exit statuses. Progress reporting is an
optional callback supplied by the caller.

## Implementation phases

### Phase 0: Establish the compatibility baseline

Tasks:

- Record supported Abaqus/Python versions and existing script invocation patterns.
- Inventory public `ODB2VTK` and `ReadableOdb` usage before removing or renaming
  methods. Retain a delegating compatibility facade where existing usage warrants
  it; avoid retaining two implementations of export logic.
- Run the seven existing regression tests and preserve their corrected results.
- Add representative characterization cases for mesh, fields, orientations,
  history, header output, and PVD generation.
- Prepare upgraded copies of the bundled ODB fixtures for local integration
  checks. Preserve the original fixtures; record the version used to upgrade.
- Record conversion duration and peak memory for a representative available ODB.
  Document its size and selection so later comparisons are reproducible.

Exit criteria: supported runtimes and preserved behaviors are written down;
synthetic baseline tests pass; integration fixture availability and limitations
are explicit. A compatible real ODB is required before final migration acceptance.

### Phase 1: Extract numerical conversion and serialization

Tasks:

- [x] Extract label/index construction, bulk-data placement, quaternion conversion,
  and history-table assembly into functions with explicit inputs and outputs.
- [x] Extract VTU/PVD, CSV, and JSON serialization behind stream-based functions.
- [x] Introduce the minimum field and history records needed to connect them.
- [x] Keep `ODB2VTK` coordinating these functions during the transition.
- [x] Replace positional `vtkData` access and parallel XML/metadata updates with
  named records as each path is extracted.

Exit criteria: conversion and serialization import without Abaqus; the recent
regressions exercise real extracted functions; representative exports retain
their numerical values, metadata, and existing schemas.

### Phase 2: Introduce the source seam and resource ownership

Tasks:

- [x] Implement `AbaqusSource` with context management and explicit ownership of the
  open database. Accept an injected source in orchestration code.
- [x] Move Abaqus subset operations, constants, and bulk-object access into this
  module. Return or yield normalized records and arrays.
- [x] Implement the in-memory test adapter against the same source contract.
- [x] Verify source and test adapters obey shared shape, ordering, identity, and
  lifetime requirements. Include real-source contract checks where Abaqus is
  available.
- [x] Retire `ReadableOdb` forwarding methods after migrating their callers, retaining
  a small compatibility shim only where needed.

Exit criteria: numerical code and writers receive no Abaqus objects; tests use
normal construction without import stubs or `__new__`; source closure is verified
on successful exports and exceptions.

### Phase 3: Establish the cohesive converter interface

Tasks:

- Introduce validated selection and output options with explicit ownership.
- Move the initialization sequence inside `export_frames` and `export_history`.
- Scope mesh indices to a fixed selection and reuse them where the source mesh
  is stable. Keep history export independent of mesh-index construction.
- Centralize filename and suffix policy, directory preparation, and completed
  output tracking.
- Preserve frame-by-frame processing. Writers should consume fields incrementally
  so refactoring does not require retaining every field or frame simultaneously.
- Define partial-failure behavior. Prefer writing each file through a temporary
  sibling and replacing the destination after successful serialization. Build a
  collection from completed outputs after a successful requested export.
- Add focused exceptions and optional progress reporting.

Exit criteria: callers export through a small interface with no ordering
preconditions; invalid requests fail before conversion; no partially written
file is presented as a completed result.

### Phase 4: Migrate entry points and parallel integration

Tasks:

- Make `odb2vtk.py` delegate to `cli.main(argv)` while preserving direct execution
  from the documented working directories.
- Keep parsing and process termination inside the CLI module. Introduce clear
  nonzero failures and zero success statuses, documenting this behavior correction.
- Preserve header-only and PVD-only invocation modes.
- Verify `multiprocess.py` can still launch the script and request collection
  generation. If failure propagation or collection scheduling must change,
  implement and test those changes explicitly rather than hiding them in moves.
- Verify paths with spaces and suffix handling across entry points.

Exit criteria: documented commands work; the CLI returns predictable statuses;
the parallel runner remains integrated; unrelated CLI feature additions are
deferred.

### Phase 5: Remove transitional code and verify the design

Tasks:

- Remove duplicate legacy implementations and unused imports. Keep compatibility
  facades only for the supported interface identified in Phase 0.
- Replace temporary tests that populate internal state with tests through the
  resulting public interfaces. Preserve every regression scenario.
- Document module responsibilities, supported runtimes, library usage, and test
  commands.
- Run semantic comparisons on real ODB exports and compare duration and memory
  with the Phase 0 baseline. Investigate regressions before accepting them.

Exit criteria: the acceptance checklist below is satisfied and remaining
limitations are documented.

## Validation strategy

### Ordinary Python CI

Run with NumPy and no Abaqus installation:

```text
python -m unittest discover -s python/tests -v
```

Cover these behaviors through the appropriate resulting interfaces:

- Multiple instances with overlapping node and element labels.
- Unsorted labels, interleaved integration points, multiple components, mixed
  block sizes, and section points.
- The two fixed history-column overwrite cases and legacy single-region output.
- Field shapes and metadata consistency, connectivity, and known orientations.
- Mesh selection ownership and validation of nonexistent names or frame indices.
- Semantic XML and CSV output, filename selection, and progress/error reporting.
- Source closure and temporary-output cleanup on failures.
- CLI behavior using an injected source factory or isolated argument parsing;
  importing pure modules must not require stubbing Abaqus imports.

Use parsed output and numerical assertions rather than brittle whitespace
snapshots. Keep focused numerical tests for difficult mapping cases, plus a small
set of export tests exercising an in-memory source through the converter.

### Abaqus integration checks

Run explicitly where Abaqus and compatible fixtures are available. Export the
same selections through the baseline and refactored implementations into
separate temporary directories. Compare mesh topology, field names, associations,
component labels, numerical values, headers, history columns, and PVD references.
Use precision-aware numerical tolerances and identify expected differences.

An XML parse alone does not prove VTK compatibility. Include a reader check using
VTK or ParaView in an optional validation environment; neither becomes a runtime
dependency of the converter.

## Work intentionally deferred

- Adding every unsupported Abaqus element type or field position.
- Redesigning history timestamps, alignment, CSV padding, or PVD time semantics.
- Changing default missing values from zero to NaN.
- Binary/compressed VTU and other performance-format changes.
- A general plugin framework, deep inheritance hierarchy, or arbitrary factories.
- A C++ refactor or Python/C++ output unification.
- Broad CLI redesign and multiprocessing tuning beyond required integration.

The new design must make these changes local and testable, but implementing them
all at once would obscure whether the architectural migration preserves behavior.

## Final acceptance checklist

- [ ] Supported runtime versions are documented and exercised where available.
- [ ] Only the source module imports Abaqus-specific modules and constants.
- [ ] The source owns ODB lifetime and closes reliably on all paths.
- [ ] Selection and mesh invariants cannot be invalidated by normal caller usage.
- [ ] Numerical transformations operate on explicit records and arrays.
- [ ] Writers have no source queries or Abaqus dependencies.
- [ ] Export callers do not need to build maps or manipulate internal state.
- [ ] Existing regression scenarios pass through the resulting interfaces.
- [ ] Documented script commands and the parallel runner remain usable.
- [ ] Existing schemas and supported numerical results are preserved, with any
      intentional behavior corrections documented separately.
- [ ] Compatible real-ODB exports have passed semantic integration checks.
- [ ] Memory remains bounded by the selected mesh and current processing data;
      measured performance changes have been assessed.
