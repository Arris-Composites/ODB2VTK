# C++ Phase 1: build and parity foundation

Completed on 2026-10-27. The current Python reference is `0fe548c`. This phase
establishes build/test infrastructure; the C++ exporter has not reached Python
behavioral or architectural parity.

## Implementation

- CMake 3.20+, C++17, target-scoped SDK configuration and CTest targets.
- SDK-independent `odb2vtk_core` library, initially containing element-family
  mapping. The existing exporter calls this module, preserving its prior
  unsupported-element logging/return behavior until numerical validation changes.
- Native build is an explicit option. SDK includes/libraries are required when
  enabled; missing dependencies now fail configuration. The historical list of
  hundreds of solver/GUI libraries is replaced with five verified dependencies.
- Native read-only metadata/open-close probe with noncopyable lifetime guards,
  explicit successful close/finalization and meaningful error statuses.
- VTK-based Python/C++ comparison inventory and strict-mode gate with seven
  positive/negative-control tests.

Build commands, runtime DLL requirements and tool usage are documented in the
[build guide](cpp-build.md).

## Input-file safety fix

The first actual C++ runs exposed an existing side effect: opening an ODB with
the default writable `openOdb` changed its bytes during both header inspection
and frame export. This was observed on disposable copies of Job-1 and the
planar fixture; original fixtures were never passed to the writable exporter.

The constructor now calls `openOdb(path, true)`. Both header and frame runs
preserve the ODB SHA-256 after this fix. All four resulting VTU files, and header
output on both fixtures, match the saved pre-fix outputs byte-for-byte. This is
the intentional conversion-path safety change in Phase 1; numerical assembly,
serialization and CLI behavior otherwise remain unchanged.

## Validation

Release build matrix: Windows x64, CMake 4.0.2, Visual Studio 2022/MSVC 19.41,
Windows SDK 10.0.22000.0, Abaqus 2025 HF1. C++17 compiled with the installed SDK.

| Check | Result |
| --- | --- |
| Fresh default build without native support | Core/test targets built; no SDK discovery or SDK DLL imports |
| Pure CTest | 1 test passed, containing 18 mapping/unsupported-input cases |
| Fresh native build | Core, exporter and smoke targets compiled/linked |
| Native CTest | Core mapping and real-ODB open/close tests passed |
| Native metadata probe | Job-1 and planar metadata match Python names/frame counts; inputs unchanged |
| Probe error paths | Missing arguments return 2; missing ODB returns 1 |
| Missing-SDK configuration | Fails with explicit SDK configuration guidance |
| VTK comparison controls | 7 tests passed in the optional validation environment |
| Native exporter integration | Two frames each from Job-1 and planar; header extraction and VTU files produced |
| Input immutability after fix | Both native copies and Python/original inputs retain initial hashes |
| Output regression after safety fix | Four VTUs and two headers byte-identical to the pre-fix baseline |

The pure executable imports only Windows/C++ runtime DLLs, not Abaqus DLLs.
The native probe uses the SDK DLL directory through process PATH. Other SDK
versions, Debug builds and non-Windows native builds remain unvalidated.

## Remaining parity inventory

The same initial ODB bytes were copied separately for Python and C++. Reference
exports include two selected frames, history and PVD. C++ header/frame commands
use the matching instance/frame selection and request history; its history flag
is currently ignored. PVD comparison records an unimplemented capability rather
than implying collection-only CLI parity already exists.

| Fixture | Frames loaded | Reported differences | Parity |
| --- | ---: | ---: | --- |
| Job-1 | 2 | 17 | Not achieved |
| Planar | 2 | 13 | Not achieved |

These are inventory entries, not failing core tests. They include flat output
names, plain-text header schema, missing history/collection output, invalid
active-vector selection on Job-1 and decoded numeric differences. Coordinates
in Job-1 differ by up to about `4.99e-7` due to C++ text precision. Planar material
orientation differs by up to `1.0`: C++ defaults absent local coordinates to the
unit x direction, whereas Python leaves zero padding. Field text precision and
float-vs-double quaternion arithmetic also require alignment. Larger and sparse
fixtures are reserved for subsequent numerical integration phases.

The [recorded build/fixture/parity evidence](validation/cpp-phase1-results.json)
contains input/code hashes, metadata probe output, pre/post safety checks and
individual differences. No performance parity claim is made: correctness and
the source/numerical seam are the next phase.
