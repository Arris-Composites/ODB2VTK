# C++ alignment with the Python exporter

Status: Phases 1 and 2 completed on 2026-10-27; Phases 3 through 5 remain pending.
See [Phase 1 results](cpp-phase1-results.md), [Phase 2 results](cpp-phase2-results.md)
and the [build guide](cpp-build.md).
Python commit `0fe548c` is the reference for
behavior, schemas, CLI modes and ASCII/binary output. This plan proposes matching
both behavior and module separation, using idiomatic C++ rather than translating
Python's implementation line by line.

## Observed gaps at the initial audit

| Area | Current C++ | Required Python behavior |
| --- | --- | --- |
| Header | `header.txt`, plain text | Named JSON file with `instances` and `steps` schema |
| History and collection | `WriteCSVFile` and `WritePVDFile` are empty | History CSV and PVD export with the existing Python schemas |
| CLI | Unchecked empty argument vectors, mandatory history flag, range syntax, exceptions return success | Shared validation, optional flags with defaults, explicit frame lists, useful error statuses |
| Paths | Flat `odb_step_frame.vtu` names; supplied suffix ignored | Parent/run-name folder, `Step_frame.vtu`, suffixes, portable leaf-name validation |
| Selection | Steps stored in `std::map` | Preserve selected instance, step and frame order; reject duplicates and invalid selections |
| Integration points | Placement stride uses the current block's integration-point count | Global output width; placement by element label and actual integration-point identity; preserve padding |
| Label lookup | `map::operator[]` inserts unknown labels silently | Reject unknown connectivity/field labels; independent namespaces per instance |
| Orientation | Always reads `S`; defaults absent local coordinates to `(1,0,0)`; buffers are not fully initialized | Optional without stress; reproduce Python's section policy and zero padding, and its double-precision quaternion calculation |
| XML | Names unescaped; active attributes contain comma-separated arrays; version `1,0` | Escaped metadata, one width-compatible active array, version `1.0` |
| Serialization | ASCII only, complete point/cell field text buffers | ASCII plus uncompressed appended raw binary; stream one numerical field at a time |
| Numeric text | Fixed/default stream precision and `to_string` geometry | Preserve declared numeric precision on reader round trips |
| Lifetime/errors | API finalization skipped on early returns; raw ODB pointer and implicit copyability | RAII, deterministic closure, failure propagation and nonzero statuses |
| Publication | Direct writes; opening errors can be silent | Temporary sibling files, atomic per-file replacement, completed-output tracking |
| Build/tests | Historical SDK paths, hundreds of libraries, no test target | Explicit SDK configuration, small verified link set, SDK-independent tests and native integration checks |

The configuration probe found Visual Studio 2022/MSVC 19.41, Windows SDK
10.0.22000.0, CMake 4.0.2 and Abaqus 2025 SDK headers/libraries installed locally.
Unmodified CMake configuration fails because compatibility with the declared
minimum of 3.2 has been removed. A temporary policy override allowed compiler
detection, but `find_package(AbqSDK)` reported a missing library list while the
project still generated build files. Compilation and native execution have not
yet been established. Probe files are outside the repository.

That paragraph records the initial probe. Phase 1 subsequently fixed build/SDK
discovery and verified native execution; current results are linked above.
It also made legacy ODB access read-only after observing input-file hash changes
on disposable copies. Numerical and output parity remain pending.

## Shared behavioral contract

- Match Python's supported element-family mapping and selected-instance order.
  Do not broaden supported cells or change connectivity ordering during parity.
- Preserve nodal, centroid, integration-point and section-point names, component
  labels, ordering and padding. Deduplicate section identities consistently.
- Match missing-stress/orientation behavior and the existing first-instance
  orientation-section policy; changes to that policy are separate work.
- Match history column names/order, sampling and zero row padding. Do not add
  timestamp alignment, timestamp columns or instance filtering as a side effect.
- Match JSON/PVD schemas, output names, suffixes and collection-only behavior.
- Support `--header`, `--odbFile`, `--instance`, `--step`, `--suffix`,
  `--writeHistory`, `--writePVD`, `--format` and `--help` with Python defaults.
  `--format ascii` stays the default; `binary` means uncompressed appended raw.
- Use Float64 coordinates, Float32 fields and Int64 topology. Binary uses
  little-endian data, UInt64 length headers and byte offsets. Preserve metadata
  and active-array selection in both formats.
- Require exact decoded geometry/topology and metadata agreement. Binary
  Float32 comparisons allow at most one ULP against Python, recording every
  difference; explicitly verify original numerical values if a difference is
  unexplained. ASCII comparisons need declared-type rounding checks, not text
  identity or six-digit default formatting. See the
  [Python rounding investigation](python-binary-serialization.md#precision-and-validation).
- Publish complete files individually; preserve existing files on failure,
  report completed frames and publish the collection only after frame success.
- Keep Python behavior unchanged while C++ catches up. Performance is measured
  only after the parity checks pass.

## Target design

Use separate modules with plain owned data between them:

| Module | Responsibility |
| --- | --- |
| Requests and records | Validated selections/output options; owned mesh snapshots, field layouts/blocks, history series and results |
| Source interface | Queries needed by conversion, without SDK types in core-facing headers |
| Abaqus source | SDK calls, native precision conversion, SDK resource ownership and current-frame handle lifetime |
| In-memory source | Real plain-data fixtures for core and failure-path testing without Abaqus |
| Mesh/field/history transformations | Validated global indexing, label placement, integration-point slices, quaternion math and history tables |
| Converter | One complete request; selection validation, preparation, field streaming, completed results and progress |
| Writers | ASCII/binary VTU, PVD, JSON and CSV from records/iterators; no SDK access |
| Output publication | Directory/path checks, temporary files, atomic replacement and cleanup |
| CLI | Parse a complete request before SDK initialization, execute it and translate errors to statuses |

Use value types and `std::vector` for owned numerical buffers. Use checked
integer sizes and conversions for mesh counts, offsets and allocation products.
Use RAII guards for SDK initialization/finalization, ODB closure and temporary
files, following the SDK's ownership rules. Resource owners must not be
implicitly copyable. Destructors must not throw.

Use one narrow source abstraction with native and in-memory adapters. A virtual
destructor and only the operations conversion actually needs provide useful
polymorphism here. Avoid a broad class hierarchy, one-method forwarding classes,
and inheritance for sharing numerical helpers. ASCII and binary writers share
metadata policies; format-specific encoding remains behind their writer seam.

SDK handles must not escape into transformation or writer modules. Numerical
fields are assembled and released individually. Prepare geometry once per
request. Do not reproduce Python-only NumPy optimizations mechanically: choose
checked C++ label lookup structures from measurements while preserving semantics.

## Phase 1: build and parity harness

1. Modernize the CMake minimum and target-scoped configuration. Verify a C++
   language level supported by the installed SDK and compiler before adopting
   features such as `std::filesystem`.
2. Replace historical SDK discovery with an explicit SDK root/include/library
   configuration and actionable required-dependency failures. Determine the
   minimal required libraries from actual compile/link probes or installed SDK
   build configuration; do not link every library in the installation.
3. Separate an SDK-independent core/test target from the native executable.
   Native SDK support must be an explicit build choice. Add CTest targets.
4. Build and run a native metadata/open-close smoke test against an upgraded
   temporary ODB. Capture runtime DLL paths and build commands reproducibly.
5. Add a Python/C++ comparison harness using the existing VTK validation
   environment. Record current C++ mismatches as inventory, not passing parity.

Exit: documented build commands, a native SDK smoke test, runnable pure tests,
and a comparison harness capable of exposing semantic differences.

## Phase 2: owned records, source seam and numerical correctness

1. Introduce validated request/value records and owned data snapshots; eliminate
   setup-order requirements from the maintained converter interface.
2. Extract the native source and implement an in-memory adapter. Support native
   single/double precision explicitly and copy SDK data into owned buffers.
3. Build geometry/maps once; detect duplicate labels, unknown connectivity,
   invalid shapes, unsupported elements and size overflow before publication.
4. Place point/cell fields using checked label lookup. Use actual integration
   points with global component stride, including sparse/interleaved rows,
   multiple blocks, missing points and overlapping labels across instances.
5. Match field discovery, section deduplication, scalar labels and orientation
   behavior, including exports without stress and padding missing orientations.
6. Assemble history independently with Python's existing column and padding
   semantics. Reject malformed requests before expensive source reads.

Exit: numerical fixtures match Python, no SDK types in core interfaces, source
ownership tests pass, and invalid input cannot silently insert labels or write
out of bounds.

## Phase 3: writers, output schemas and safe publication

1. Implement stream-based ASCII with adequate round-trip precision, XML/JSON/CSV
   escaping and shared metadata/active-array policies.
2. Implement matching binary headers, offsets and payloads, with bounded writes
   and one-field-at-a-time consumption. Test endian handling and empty arrays.
3. Implement JSON headers, history CSV and PVD schemas/naming from Python.
4. Implement atomic replacement on the host platform without deleting the old
   destination first. Propagate opening/writing/closing/replacement errors.
5. Track completed frames and preserve previous files/collections on failure.
   Include deliberate serialization, source, progress and publication failures.

Exit: VTK reads both formats without warning/error events; schemas and metadata
match Python; partial writes cannot replace valid destination files.

## Phase 4: CLI and execution parity

1. Replace unchecked argument handling with a parser that creates one complete
   request. Validate empty/missing values, unknown flags, flags with extra values,
   duplicates, strict frame lists and output conflicts.
2. Add all shared flags/defaults, including suffix, history, collection-only and
   ASCII/binary selection. Preserve explicit step order rather than sorting it.
3. Handle help/invalid arguments before opening an ODB; use statuses 0 for
   success, 2 for argument/selection errors and 1 for runtime failures.
4. Guarantee SDK finalization on every exit and close the source before reporting
   successful completion. Report completed outputs when a later operation fails.
5. Match the serial CLI first. Do not add a second unverified parallel scheduler.
   Assess native-worker integration with the existing Python coordinator only
   after the executable's contract is stable; it needs a verified receipt
   protocol if the same coordinator is to launch it.

Exit: equivalent serial commands produce equivalent named outputs, with failure
statuses and lifetimes verified through actual processes. Parallel coordination
remains an explicit follow-up unless included in the agreed scope.

## Phase 5: integration, performance and retirement of old paths

1. Generate Python and C++ exports from the exact same compatible ODB bytes:
   real Job-1, planar, generated compact and sparse labels, single/multiple
   frames and multiple instances. Include missing stress and section/IP fixtures.
2. Compare geometry, connectivity, field names/types/components/values, active
   metadata, JSON, CSV and PVD references. Cover selected ordering and failures.
   Record any tolerance with affected fields/counts and its numerical cause.
3. Run repeated alternating native processes in release builds. Record exclusive
   workflow phases, total time, peak process memory, file sizes and reader time;
   keep imports/startup and cache conditions explicit.
4. Optimize measured C++ hotspots. Consider dense/sparse label tables and mesh
   reuse only when they reduce time or memory in the native implementation.
5. Remove the old monolithic implementation and obsolete build instructions
   once the maintained interface is complete; do not retain unused shims.

Exit: a recorded parity matrix and reproducible native benchmark report. Native
compilation alone is not evidence of output correctness or performance parity.
