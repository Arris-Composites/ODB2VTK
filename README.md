![abaqusCAE](res/abaqusCAE.png)![U+2192.svg](res/U+2192.svg.png)![ParaView_Logo](res/ParaView_Logo.png)

# Abaqus output database to VTK converter

## Introduction

Abaqus output database (.odb extension) is a binary file native to Abaqus. To access the data from ODB file, without reverse engineering, is to use official Abaqus APIs which are provided in Python or C++. This project provides a converter implemented in Python and C++. The C++ version is considerably faster than the Python version but it needs proper configuration to successfully build from the source. This work is inspired by [Liujie](https://github.com/Liujie-SYSU/odb2vtk). And all other similar work doesn't satisfy my needs since I need a converter which is more general and extensible. So I ended up implement my own version of it. This converter will:

1. Convert all the field outputs which exist in the ODB file.
2. Convert data at integrations points / section points and material orientation.
3. Map Abaqus element to VTK cell at your will.

If you want to know more about the design of ODB2VTK, checkout this [article](https://www.sciencedirect.com/science/article/pii/S2352711023000274).

## Usage Python

![](res/odb2vtk_tutorial.gif)
Run the following commands from the repository's `python` directory (`cd python`
from the repository root). ODB access requires Abaqus Python. The package entry
points replace the removed `odb2vtk.py` and `multiprocess.py` scripts; the old
`ODB2VTK` and `ReadableOdb` library interfaces are no longer supported.

For library use, import `AbaqusSource`, `Converter`, `Selection`, and
`OutputOptions` from `odb2vtk_core`. See the [library guide](doc/python-converter-interface.md).
From other working directories, set `PYTHONPATH` to the repository's absolute
`python` directory.

`abaqus python -m odb2vtk_core --header 1 --odbFile <my_odb_file_path>/my_odb_file.odb`

This will open the odb file, extract instances, steps, and frames, and save them into a JSON file in the same directory of the odb file.

![json_header](res/json_header.png)

`abaqus python -m odb2vtk_core --header 0 --instance "Part-1" --step "Step-1:0,1" --odbFile <my_odb_file_path>/my_odb_file.odb`

With 0 passed to header, it will write vtu data for instance "Part-1" at "Step-1" with frame number 0 and 1.

Add `--format binary` to write uncompressed appended binary VTU files. The
default is `--format ascii`; both modes use the same `.vtu` names and PVD
references. Binary avoids decimal formatting and works with VTK/ParaView readers.
The option also works with `python -m odb2vtk_core.parallel`. See the
[binary serialization results](doc/python-binary-serialization.md) for timing,
file sizes, precision and validation details.

`abaqus python -m odb2vtk_core --header 0 --instance "Part-1" "Part-2" --step "Step-1:0,1" "Step-2:0,1,2,3,4,5" "Step-3:0,1,2,3" --odbFile <my_odb_file_path>/my_odb_file.odb`

The above command will convert frame 0 to 1 in step 1, 0 to 5 in step 2, and 0 to 3 in step 3 for instance "Part-1" and "Part-2".

`python -m odb2vtk_core.parallel --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" "Step-3:2" --odbFile <my_odb_file_path>/my_odb_file.odb`

The runner first validates the complete request in Abaqus, then converts one frame
per worker. The two frame conversions below run in parallel; the final collection
command runs only after both succeed. Use `--jobs 2` to limit concurrency and
`--writeHistory 1` to export history once after the frame workers finish.

`abaqus python -m odb2vtk_core --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" --odbFile <my_odb_file_path>/my_odb_file.odb`

`abaqus python -m odb2vtk_core --header 0 --instance "Part-1" "Part-2" --step "Step-3:2" --odbFile <my_odb_file_path>/my_odb_file.odb`

`abaqus python -m odb2vtk_core --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" "Step-3:2" --odbFile <my_odb_file_path>/my_odb_file.odb --writePVD 1`

The last command will generate a .pvd file.
Suppose the odb directory looks like this

```

project

│───Job-1.odb  

```

After `python -m odb2vtk_core.parallel --header 0 --instance "Part-1" "Part-2" --step "Step-1:1" "Step-3:2" --odbFile ./Job-1.odb` has been executed, we will get

```

project

│───Job-1.odb  
└───Job-1
    │____Job-1.pvd
	│____Step-1_1.vtu
	│____Step-3_2.vtu

```

If you are converting different instances from the odb with the same step and frame, use '--suffix name' to append 'name' to the folder to avoid name clash.

From the repository root, the numerical conversion and serialization modules in
`python/odb2vtk_core` can be tested with ordinary Python and NumPy, without an
Abaqus installation:

```text
python -m unittest discover -s python/tests -v
```

See the [Python refactor plan](doc/python-refactor-plan.md) and
[Phase 1 results](doc/python-phase1-results.md) for the numerical module design.
The [source interface](doc/python-source-interface.md) documents ODB ownership
and source injection; [Phase 2 results](doc/python-phase2-results.md) records its validation.
New library callers can use the [converter interface](doc/python-converter-interface.md)
to export immutable requests without constructing maps. See
[Phase 3 results](doc/python-phase3-results.md) for validation and publication behavior.
The [CLI and parallel runner guide](doc/python-cli.md) documents statuses, shared
argument validation, and verified worker completion; see
[Phase 4 results](doc/python-phase4-results.md) for the integration checks.
The [Python architecture guide](doc/python-architecture.md) describes the final
module responsibilities, runtime support, and compatibility migration.
[Phase 5 results](doc/python-phase5-results.md) records VTK reader checks and
export duration/memory measurements.

## Build C++ with CMake

The C++ implementation is being aligned with the current Python exporter.
[Phase 1](doc/cpp-phase1-results.md) establishes a C++17 build, SDK-independent
tests, Abaqus 2025 integration probes and a semantic comparison harness.
[Phase 2](doc/cpp-phase2-results.md) adds owned source records and numerical
parity. [Phase 3](doc/cpp-phase3-results.md) adds ASCII/binary writers, JSON/CSV/PVD
and safe publication. CLI parity remains pending; see the [alignment plan](doc/cpp-parity-plan.md).

From the repository root, build the core without Abaqus:

```powershell
cmake -S cpp -B cpp/build/pure -G "Visual Studio 17 2022" -A x64
cmake --build cpp/build/pure --config Release
ctest --test-dir cpp/build/pure -C Release --output-on-failure
```

To build the native executable, configure a separate directory with
`-DODB2VTK_BUILD_NATIVE=ON` and
`-DABQ_SDK_ROOT=C:/ABAQUS/2025/EstProducts`. See the
[build guide](doc/cpp-build.md) for complete commands, required SDK libraries,
runtime DLL paths and optional real-ODB tests. Native builds require an installed
SDK; CMake no longer searches historical installation paths or links every SDK
library.

The existing native CLI now writes `Job-1.json`, `Job-1/Step-1_0.vtu` and a PVD:

```text
ODB2VTK.exe --header 1 --odbFile C:/temp/Job-1.odb
ODB2VTK.exe --header 0 --odbFile C:/temp/Job-1.odb --instance L-SHAPE-PART-1 --step Step-1:0,1 --writeHistory 0
```

ODB files must be compatible with the installed SDK. History, collection-only
and binary modes are available through the [maintained C++ interface and validation
probe](doc/cpp-writers.md); their normal CLI flags/defaults will be aligned in
Phase 4. Current native ODB access is read-only, with input hashes verified.

## Convert a range of frames by one command

Now a new parse rule which accepts a range of frames has been added to the C++ version. This will be convenient to convert a large quantity of consecutive frames by one command.

```
odb2vtk.exe --header 0 --odbFile C:/test/mixed_elements/collision.odb --instance PART-1-1 PART-2-1 --step  Step-1:0-1000 --writeHistory 0
```

converts frames ranging from 0 to 1000. So, it will generate 1001 individual vtu files. Do not mix it with single digit frame arguments.

## Abaqus Version Updates
Both the C++ and Python builds have been updated for Abaqus 2023.

This describes the historical release. The refactored Python exporter is
validated with Abaqus 2025 HF1 / Python 3.10 on Windows. Its pure conversion
modules are also tested with CPython 3.12. Python 2 is unsupported; Abaqus 2023
has not been revalidated. See the [runtime details](doc/python-architecture.md#supported-and-validated-runtimes).

The C++ Phase 1 Release build and native SDK probes are also validated with
Abaqus 2025 HF1 on Windows; full output parity remains pending.

## TODOS

- [ ] implement writeHistory for C++ version.
- [ ] implement writePVD for C++ version.
