# Tool setup and commands

## Environment

The converter requires a checkout containing `python/odb2vtk_core` and an Abaqus
installation that can read the input ODB. Native conversion is validated with
Abaqus 2025 HF1 / Python 3.10 on Windows. The host parallel runner uses ordinary
Python 3.10–3.12 and an `abaqus` launcher on PATH.

`ODB2VTK_ROOT` below is a convenient way to identify the checkout for the agent;
the package itself is discovered through `PYTHONPATH`. Set it for the current
shell/process, preserving other module-search paths. Substitute actual locations.

PowerShell:

```powershell
$env:ODB2VTK_ROOT = 'C:/tools/ODB2VTK'
$packagePath = Join-Path $env:ODB2VTK_ROOT 'python'
$env:PYTHONPATH = $packagePath + [IO.Path]::PathSeparator + $env:PYTHONPATH
abaqus python -m odb2vtk_core --help
```

POSIX shell:

```sh
export ODB2VTK_ROOT=/path/to/ODB2VTK
export PYTHONPATH="$ODB2VTK_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"
abaqus python -m odb2vtk_core --help
```

Alternatively, run from the checkout's `python` directory. Resolve the ODB's
absolute path first so a directory change does not change which file is selected.
Confirm help contains `--odbFile` and `--format`, rather than trusting the launcher's
status alone. Use the actual installed launcher for serial commands. The host
parallel runner specifically resolves `abaqus` from PATH.

## Inspect metadata

```text
abaqus python -m odb2vtk_core --header 1 --odbFile "C:/work/Job-1.odb" --suffix _inspect
```

Read `C:/work/Job-1_inspect.json`. It contains `instances` and `steps`; each step
includes frame labels such as `Step-1-frame-0`. Convert the listed indices into
explicit `--step` tokens. The examples below assume inspection found `Part-1`
and `Step-1` with frames 0 and 1; substitute the actual metadata.

## Serial frames

```text
abaqus python -m odb2vtk_core --header 0 --odbFile "C:/work/Job-1.odb" --instance "Part-1" --step "Step-1:0,1" --suffix _selected
```

ASCII is the default. To export binary and history CSV:

```text
abaqus python -m odb2vtk_core --header 0 --odbFile "C:/work/Job-1.odb" --instance "Part-1" --step "Step-1:0,1" --format binary --writeHistory 1 --suffix _selected
```

For several instances/steps, provide additional values after their flags:
`--instance "Part-1" "Part-2" --step "Step-2:1,0" "Step-1:0,1"`.
Requested order is preserved. Use explicit lists, not `0-100` ranges. Instance,
step, and frame duplicates are rejected. Quote values for the current shell;
for scripted invocations, pass argument arrays to `subprocess.run` instead of
interpolating user paths or metadata into shell command strings.

The CLI selects instances and frames; it exports all supported fields. It has
no field-filter or output-directory flag. Use the public API below for a custom
destination. Binary means uncompressed appended raw VTU, with the same `.vtu`
extension as ASCII.

## Index existing VTUs

```text
abaqus python -m odb2vtk_core --header 0 --odbFile "C:/work/Job-1.odb" --instance "Part-1" --step "Step-1:0,1" --writePVD 1 --suffix _selected
```

Serial frame mode does not create a collection automatically. `--writePVD 1`
selects collection-only mode and requires the referenced VTUs to exist under
the same suffix. It does not convert missing frames. `--writeHistory 1` can also
be used in this mode.

## Parallel frames

```text
python -m odb2vtk_core.parallel --header 0 --odbFile "C:/work/Job-1.odb" --instance "Part-1" --step "Step-1:0,1" --format binary --writeHistory 1 --suffix _parallel --jobs 2
```

Run this coordinator in ordinary Python with `abaqus` on PATH. It validates the
complete request in Abaqus, converts one frame per worker, then exports history
once and writes a PVD after all frames succeed. Without `--jobs`, concurrency
defaults to the host CPU count, capped by selected frame count. `--jobs 1` keeps
the same receipt-verifying workflow with one worker at a time; it still writes
a collection. Header-only and collection-only requests also work through this
entry point.

The host runner transports request values as JSON. This avoids the quoting and
Unicode-transcoding pitfalls of passing arbitrary values through an Abaqus
Windows batch launcher. Use it when its collection-producing behavior fits the
request; preserve exact paths and names rather than changing characters to make
a direct batch invocation work.

## Output layout

For `C:/work/Job-1.odb` and suffix `_selected`, the run name is `Job-1_selected`:

```text
C:/work/
|-- Job-1.odb
|-- Job-1_selected.json          header mode
`-- Job-1_selected/
    |-- Step-1_0.vtu
    |-- Step-1_1.vtu
    |-- Job-1_selected.csv       when history is requested
    `-- Job-1_selected.pvd       collection mode or successful parallel export
```

The run name uses the ODB filename before its first dot, plus the suffix:
`job.results.odb` becomes `job`, not `job.results`. Different such inputs in the
same directory need distinct suffixes to avoid collisions. A suffix is a filename
component, not a directory path. Portable filename validation rejects separators,
reserved device names, control characters, and trailing dots/spaces.

## Custom destination with the public API

Run this code in a script using `abaqus python script.py`, with the package path
configured as above. Supply actual paths and selections. This example explicitly
requests a PVD as well as frames and history.

```python
from odb2vtk_core import AbaqusSource, Converter, OutputOptions, Selection

selection = Selection(["Part-1"], [("Step-1", [0, 1])])
outputs = OutputOptions(
    "C:/exports", "Job-1", suffix="_selected",
    write_pvd=True, vtu_format="binary",
)
with AbaqusSource.open("C:/work/Job-1.odb") as source:
    converter = Converter(source)
    converter.validate_frames(selection, outputs)
    converter.validate_history(selection, outputs)
    history = converter.export_history(selection, outputs)
    result = converter.export_frames(selection, outputs)
for path in history.paths + result.paths:
    print(path)
```

The context manager closes the source. CLI examples retain their no-PVD serial
default; public `OutputOptions` defaults to `write_pvd=True`, so choose it explicitly.

## Completion and statuses

The Python entry points return 0 on success, 2 for argument/selection errors,
1 for runtime failures, and 130 on interruption. Some Abaqus Windows launchers
return 0 even when Python fails. Examine diagnostics and fresh artifacts; use
the host runner's receipt checks when its behavior fits the task.

Normal completion produces `Completed:` messages. Capture both stdout and stderr.
Runtime failures can leave already-completed files; report those paths accurately.
The tool publishes complete files individually and keeps the original ODB read-only.
