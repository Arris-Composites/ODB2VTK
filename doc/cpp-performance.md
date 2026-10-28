# Reproducing C++/Python performance measurements

Build Release using the [build guide](cpp-build.md), including test targets.
`odb2vtk_profile_exports` is native validation tooling, not a new product CLI.
It uses the maintained source/exporter to write history, frames and a collection.
The ordinary CLI is documented [separately](cpp-cli.md).

In a Python environment with NumPy and VTK:

```powershell
$env:PATH = 'C:\ABAQUS\2025\EstProducts\win_b64\code\bin;' + $env:PATH
python cpp/validation/benchmark_exports.py --cpp-profile cpp/build/native/Release/odb2vtk_profile_exports.exe --odb C:/temp/Job-1.odb --instance Part-1 --frames 0,1 --output C:/temp/cpp-python-benchmark --repeats 3
```

Both implementations open the **same ODB path**, not merely similar models.
The tool verifies the input SHA-256 throughout. Each implementation/format gets
one discarded warmup and three measured fresh processes, alternating their order.
Separate phase probes follow the primary measurements. Generated outputs go to
distinct suffix directories alongside the input; reports go under `--output`.
Repeated runs replace the same outputs and assert deterministic file hashes.

The benchmark records workflow and process-wall times, process peak working set,
file sizes, exact decoded parity and warm VTK reader time. The reader measurements
follow correctness reads and alternate order. They exclude Python/VTK imports.
Writes are buffered; there is no `fsync` or cold/network-storage guarantee.
Three samples expose variability but do not establish a general statistical
performance guarantee. Inspect the stored sample ranges as well as medians.

Workflow timing covers ODB open, history, mesh preparation, field discovery/read/
assembly, VTU serialization, publication, PVD and close. Python's package/SDK
imports occur before its workflow timer; native API initialization occurs inside
`odb_open`. Process wall time includes launch, imports/loading, report writing
and shutdown. Those definitions are recorded explicitly rather than labeling
all outside-workflow time as startup. Peak memory includes each runtime/SDK.

## Large compact/sparse fixtures

Generate new files with Abaqus Python, without running a solver:

```powershell
abaqus python python/validation/create_benchmark_odb.py C:/temp/compact.odb 20000 4 1
abaqus python python/validation/create_benchmark_odb.py C:/temp/sparse.odb 20000 4 11
python cpp/validation/benchmark_exports.py --cpp-profile cpp/build/native/Release/odb2vtk_profile_exports.exe --odb C:/temp/compact.odb --instance PART-1-1 --frames 0,1,2,3 --output C:/temp/compact-benchmark
python cpp/validation/benchmark_exports.py --cpp-profile cpp/build/native/Release/odb2vtk_profile_exports.exe --odb C:/temp/sparse.odb --instance PART-1-1 --frames 0,1,2,3 --output C:/temp/sparse-benchmark
```

Each fixture has 160,000 nodes and 20,000 disconnected C3D8R cells, with U/RF,
four nodal scalars and stress. These exercise scaling and label density; they do
not represent every solver workload, cell family or field layout. The generator
refuses to overwrite an existing file.

## Individual native phase probes

```powershell
cpp/build/native/Release/odb2vtk_profile_exports.exe C:/temp/compact.odb PART-1-1 0,1,2,3 _cpp_probe binary C:/temp/cpp-probe.json
```

Append `--no-phases` for a control run. The internal session uses steady-clock
scopes and subtracts nested time, including assembly performed in a source block
callback. Without a session, scopes perform no clock reads or recording. Normal
export commands do not enable profiling. No public source/writer interface or
CLI flag was added for implementation instrumentation.

The initial native ASCII probe identified serialization as the dominant cost.
The implemented optimization uses C++17 `to_chars` and a 64 KiB numerical text
buffer, preserving 17-digit Float64 round trips and Int64 decimal topology.
Binary encoding and assembly are unchanged. Both numerical encodings use
bounded writes; no complete field text buffers are retained.

To reproduce the older stream-formatting baseline, apply
[the validation patch](validation/cpp-ascii-stream-baseline.patch) to an isolated
checkout of the original Phase 5 revision, `c76f485`, and build its profiling
target. The patch targets that revision's source formatting. It restores only
ASCII numerical formatting and retains the same profiling/assembly/publication
code. It is a benchmark artifact, not an alternate supported writer. Pass that
executable as `--baseline-cpp-profile PATH` when benchmarking the optimized build.
It adds baseline warmups/samples/probes to the alternating sequence.

See [Phase 5 results](cpp-phase5-results.md) for measured values, parity coverage
and the machine-readable samples.
