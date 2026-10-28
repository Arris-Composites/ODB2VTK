# C++ output interface

`odb2vtk_core/exporter.hpp` exposes complete export operations over a borrowed
`Source`. Native SDK details remain in `AbaqusSource`. For example:

```cpp
#include "odb2vtk_core/abaqus_source.hpp"
#include "odb2vtk_core/exporter.hpp"
using namespace odb2vtk_core;

AbaqusSource source("C:/work/Job-1.odb");
Selection selection({"Part-1"}, {{"Step-1", {0, 1}}});
auto outputs = OutputOptions::from_odb(
    "C:/work/Job-1.odb", "_cpp", true, VtuFormat::binary);
Exporter exporter(source);
exporter.export_header(outputs);
exporter.export_history(selection, outputs);
auto result = exporter.export_frames(selection, outputs);
source.close();
```

Omitting the format selects ASCII. Files are named
`Job-1_cpp/Step-1_0.vtu`, `Job-1_cpp/Job-1_cpp.csv`,
`Job-1_cpp/Job-1_cpp.pvd` and `Job-1_cpp.json`. `export_frames` publishes the
collection by default; `write_pvd=false` disables that step.
`export_collection` indexes existing VTUs and rejects missing files without
converting geometry or fields. The caller controls source closure.

`ExportFailure::result()` reports files already published if a later operation
fails. Its `cause()` retains the original exception. Existing current-frame and
collection files survive failed replacement. An optional `Progress` callback
receives completion events after their receipts are recorded.

`VtuWriter` is the lower-level stream sink used by `Converter::convert`. It
validates field metadata/order and tuple counts. Direct callers own the stream,
mesh lifetime and publication; a stream containing a failed serialization must
be discarded. `atomic_output(path, callback)` provides safe per-file publication
for direct writer use. Standalone `write_header`, `write_history` and
`write_collection` functions accept only plain records.

## Validation commands

Build using the [C++ build guide](cpp-build.md). The native validation probe
supports both formats independently of the legacy CLI parser:

```powershell
$env:PATH = 'C:\ABAQUS\2025\EstProducts\win_b64\code\bin;' + $env:PATH
cpp/build/native/Release/odb2vtk_export_probe.exe C:/work/Job-1.odb C:/temp/cpp-output binary Part-1 0,1
```

This probe writes header, history, frames and collection, then explicitly closes
the source. It currently targets `Step-1`; it is validation tooling, not the
replacement CLI. Normal `ODB2VTK --format` parsing is Phase 4.

With Abaqus on PATH and an ordinary Python environment containing NumPy/VTK:

```powershell
python cpp/validation/validate_writer_parity.py --probe cpp/build/native/Release/odb2vtk_export_probe.exe --odb C:/work/Job-1.odb --instance Part-1 --output C:/temp/writer-parity
python cpp/validation/validate_writer_edges.py --fixture-exe cpp/build/pure/Release/odb2vtk_writer_fixture.exe --output C:/temp/writer-edges
```

The parity command creates separate Python/C++ directories for both formats,
compares decoded arrays and auxiliary files, checks raw binary offsets/lengths,
and verifies the input hash. It calls Abaqus Python to produce the reference.
Use `--frames 0` for a single frame. Edge checks record the shared VTK ASCII
negative-infinity reader limitation and midpoint rounding separately; see
[Phase 3 results](cpp-phase3-results.md).
