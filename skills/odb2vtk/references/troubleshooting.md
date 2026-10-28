# Conversion troubleshooting

## `No module named odb2vtk_core`

Check the checkout really contains `python/odb2vtk_core/__main__.py`. Set
`PYTHONPATH` to that checkout's absolute `python` directory in the process that
launches the command, or run from that directory. Installing the skill alone
does not put the converter on Python's import path. Verify module help before
retrying the conversion.

## Abaqus modules unavailable

Serial ODB access runs in Abaqus Python. Ordinary Python can run module help
and the host parallel coordinator, but cannot open an ODB by installing NumPy
alone. Use an available Abaqus launcher for conversion. For the host runner,
ensure `abaqus` resolves on PATH; there is no `--abaqus` CLI option.

## Input cannot be opened

Resolve the absolute ODB path and confirm it is a file before changing working
directories. Check the error identifies the intended input. A copied relative
path may resolve differently after entering the checkout's `python` directory.

Use an Abaqus installation compatible with the ODB. If an upgrade is necessary,
upgrade a separate copy using that installation's supported procedure and keep
the original. Report compatibility errors instead of retrying the same failing
command unchanged.

## Instance, step, or frame selection fails

Inspect fresh header JSON and use its actual names. Frames are zero-based,
explicit comma-separated indices. `Step-1:0,1` is valid; ranges such as
`Step-1:0-1`, negative indices, and duplicates are invalid. Multiple step tokens
follow one `--step` flag. The last colon separates a step name from its indices;
output names must still satisfy portable filename rules.

If the request asks for only particular fields, explain that the current CLI
exports all supported fields for the selected instances/frames. Do not fabricate
a field-selection flag.

## No PVD, or collection-only mode reports missing VTUs

Serial frame export does not generate a PVD. Convert the frames first, then use
the same instance/step/frame selection and suffix with `--writePVD 1`.
Collection-only mode does not regenerate missing VTUs. Successful parallel frame
export already performs the collection stage.

## Binary VTU looks like XML or an XML parser fails

VTU contains XML metadata in either format. Binary output has `format="appended"`
arrays and an `AppendedData` section with raw bytes. Its `.vtu` extension is
unchanged. Use VTK/ParaView to read the complete binary file; a generic XML parser
cannot validate raw appended payloads. VTK is optional reader tooling, not a
conversion dependency.

## Output conflicts, denied writes, or locked files

CLI outputs live beside the ODB, under the run name described in
[usage](usage.md#output-layout). Check the parent is writable, the target is not
a directory, and the destination is not locked by another application. Use the
requested suffix consistently; choose a distinct one for independent selections.
For another destination directory, use the documented public API rather than
inventing a CLI flag. Record completed files after a later failure; publication
is atomic per file, not a rollback of the entire request.

## Launcher reports success but output is absent or stale

Capture the actual messages and check each expected file was published during
this invocation. Existing output from an earlier run is insufficient. Some
Abaqus Windows launchers mask Python's failure status. The host parallel runner
checks new structured receipts and expected artifacts in addition to launch
status. `--jobs 1` provides those checks without concurrent workers when its
automatic PVD stage fits the request. Preserve that distinction when selecting
the execution mode.

## Partial export or omitted fields

Report the paths that completed and the original error. The host runner stops
scheduling new work after a worker failure and does not publish a new collection
for an incomplete frame request. An older collection may still exist; it does
not prove the new run succeeded. The converter may report omitted fields for
unsupported positions. Include those diagnostics rather than claiming that
every field was exported.
