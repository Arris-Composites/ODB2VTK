# C++ build and Phase 1 validation

Tested on 2026-10-27 with CMake 4.0.2, Visual Studio 2022/MSVC 19.41,
Windows SDK 10.0.22000.0 and Abaqus 2025 HF1. The project requires CMake 3.20+
and C++17. Other SDK releases/platforms and Debug builds have not been validated.

Use fresh build directories when migrating from the historical CMake files.
No SDK files, libraries or DLLs are bundled in this repository.

## Build without Abaqus

From the repository root in PowerShell:

```powershell
cmake -S cpp -B cpp/build/pure -G "Visual Studio 17 2022" -A x64
cmake --build cpp/build/pure --config Release
ctest --test-dir cpp/build/pure -C Release --output-on-failure
```

The default `ODB2VTK_BUILD_NATIVE=OFF` builds the SDK-independent core and its
tests. SDK discovery is not performed. The initial core module contains the
element-family mapping used by the existing exporter; numerical extraction and
the source interface follow in Phase 2. Tests cover all 13 families, matching
precedence/suffix behavior and rejection of unsupported values (18 cases).

## Build with Abaqus 2025

Point `ABQ_SDK_ROOT` to the `EstProducts` directory containing `SMAOdb`:

```powershell
$sdk = "C:/ABAQUS/2025/EstProducts"
cmake -S cpp -B cpp/build/native -G "Visual Studio 17 2022" -A x64 -DODB2VTK_BUILD_NATIVE=ON "-DABQ_SDK_ROOT=$sdk" "-DODB2VTK_TEST_ODB=C:/temp/Job-1.odb"
cmake --build cpp/build/native --config Release
$env:PATH = "$sdk/win_b64/code/bin;$env:PATH"
ctest --test-dir cpp/build/native -C Release --output-on-failure
```

`ODB2VTK_TEST_ODB` is optional. Supply an existing ODB compatible with the SDK;
the checked-in historical fixtures need upgrading for Abaqus 2025. The native
smoke test is registered only when a fixture is supplied. The target executable
is still built when native support/testing are enabled without a fixture.

Native targets are `ODB2VTK` (the current exporter) and `odb2vtk_sdk_smoke`.
Missing required SDK paths/libraries cause configuration to fail with an
actionable message. For customized installations, the `AbqSDK_INCLUDE_DIR`,
`AbqSDK_PUBLIC_INCLUDE_DIR` and per-library `AbqSDK_<component>_LIBRARY` cache
entries can be set explicitly.

The imported target `AbqSDK::Odb` supplies SDK includes, Windows definitions and
five direct import libraries verified through symbol inspection and linking:

- `ABQSMAOdbApi`
- `ABQSMAOdbCore`
- `ABQSMABasCoreUtils`
- `ABQSMABasAlloc`
- `ABQSMABasShared`

Runtime DLLs and their transitive dependencies remain in the SDK's `code/bin`
directory. Add it to the launching process's PATH; copying those DLLs into the
repo or linking every installation library is unnecessary. Native SDK targets
were validated in Release with the compiler's dynamic runtime defaults.

The smoke probe opens the ODB read-only, reports instance names and step/frame
counts as JSON, explicitly closes the database and finalizes the API before
printing success. RAII guards cover failure cleanup. It returns 2 for missing
arguments and 1 for a failed ODB open. These statuses describe the probe; the
legacy exporter's CLI/status alignment remains pending.

## Compare Python and C++ output

Use disposable compatible fixture copies and distinct output directories. The
Phase 1 comparison deliberately reports remaining differences rather than
claiming parity. The read-only fix prevents ODB changes, but the current exporter
still lacks several Python behaviors and safe per-file publication.

Generate a Python reference report with `python/validation/profile_exports.py`,
then run the C++ executable on the matching instance/step/frame selection.
The current C++ output is flat, named `Job-1_Step-1_0.vtu`, while Python writes
`Step-1_0.vtu` under the run directory. Current C++ header output is plain
`header.txt`; history/PVD methods remain empty. Those gaps are expected inventory.

In an ordinary Python environment with NumPy and VTK:

```text
python cpp/validation/compare_exports.py --python-report C:/temp/python.json --cpp-vtu C:/temp/cpp/Job-1_Step-1_0.vtu C:/temp/cpp/Job-1_Step-1_1.vtu --reference-header C:/temp/python-header.json --cpp-header C:/temp/cpp/header.txt --report C:/temp/parity.json
python -m unittest discover -s cpp/validation/tests -v
```

Pass `--cpp-history` and `--cpp-pvd` when those outputs become available. History
tables are compared by decoded header/numeric cells, and collection metadata by
attributes/times/parts/references, rather than XML layout. Numeric mesh/topology
checks are exact; Float32 fields permit at most one ULP, recorded explicitly.

Default exit 0 means the inventory was written, **not** that parity passed.
Use `--strict` to return 1 when `parity` is false. The seven comparison-tool tests
cover matching data, numerical/label differences, explicit one-ULP recording,
missing files, strict status, auxiliary schemas/layout and malformed XML.

See [Phase 1 results](cpp-phase1-results.md) for the native fixture results,
read-only safety fix and remaining gaps, and the [alignment plan](cpp-parity-plan.md)
for the subsequent phases.
