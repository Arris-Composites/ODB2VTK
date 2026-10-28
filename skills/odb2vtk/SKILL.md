---
name: odb2vtk
description: Inspect Abaqus ODB metadata and convert selected instances, steps, and frames to VTU, PVD, and history CSV using odb2vtk_core. Use for ODB-to-VTK exports, ASCII or binary output, parallel conversion, and troubleshooting these conversions.
---

# ODB2VTK

Use the existing `odb2vtk_core` Python package through the shell. Run conversion
in Abaqus Python; run the parallel coordinator in ordinary Python.

## Locate the tool

Read [usage](references/usage.md) for environment setup, commands, and output paths.

Find the checkout containing `python/odb2vtk_core`. Use `ODB2VTK_ROOT` when supplied,
otherwise use the current checkout or the user's tool location. The installed
skill directory and converter checkout may be in different places.

Resolve the input ODB to an absolute path before changing directories. Verify the
Abaqus launcher and package discovery with the documented help command. If the
checkout or launcher cannot be located, request that missing location.

## Convert the request

1. Resolve the requested ODB, instances, steps, frames, format, suffix, and any
   history or collection request. Preserve explicit choices and ordering.
2. When selection metadata is unknown, export and read the header JSON. Use its
   instance names and frame indices to resolve the selection; clarify remaining
   ambiguity instead of guessing names. Choose a nonconflicting inspection suffix
   if an existing header belongs to another task. Header inspection writes JSON
   beside the ODB; it does not modify the ODB.
3. Build the appropriate command from the usage reference. Frame indices are
   explicit comma-separated lists. ASCII is the tool default; use binary when
   requested. The converter exports all supported fields for the selection.
4. Execute the request. Serial frame export produces VTUs and optional history;
   collection-only mode indexes existing VTUs. Parallel frame export schedules
   Abaqus workers and publishes a PVD after success. Use the requested job limit.
5. Verify completion using the criteria below. On failure, read
   [troubleshooting](references/troubleshooting.md), report the actual diagnostic
   and completed files, and correct its cause before retrying.

For an output directory outside the ODB's parent, use the public Python API example
in the usage reference. Its `OutputOptions` controls the destination explicitly.
Use the user's suffix when supplied; choose distinct output names for independent
selections that would otherwise collide. Keep the original ODB unchanged.

## Verify and report

- Determine the expected output paths before execution. Check that every requested
  file was produced by this invocation, using completion messages and fresh file
  metadata. Pre-existing files alone do not establish success.
- On Abaqus installations that mask Python exit statuses, check diagnostics and
  fresh artifacts as well as the process status. The host parallel runner verifies
  structured worker receipts; `--jobs 1` is useful when its collection-producing
  behavior fits the request.
- Check the header JSON, CSV presence when requested, and PVD references when a
  collection was requested. Use a VTK reader when available for decoded VTU
  validation. Appended raw binary VTUs are not ordinary parseable XML documents.
- Report the resolved selection, format, output paths, and any omitted-field
  diagnostics or partial results. Claim success only for verified artifacts.

This skill performs conversion and inspection. Numerical interpretation of the
simulation results requires a separate analysis request.
