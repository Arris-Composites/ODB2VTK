# Python refactor: Phase 1 results

Completed: 2026-10-26.

## Implementation

The existing `ODB2VTK` class remains the coordinator and the existing command
line entry point. Its numerical transformations and file serialization now
delegate to `python/odb2vtk_core`:

| Module | Responsibility |
| --- | --- |
| `models.py` | Named field layouts, field arrays, mesh records, history records, collection entries |
| `mesh.py` | Instance-scoped label maps, mesh topology assembly, existing element-family mapping |
| `fields.py` | Point/cell data placement and quaternion-to-direction conversion |
| `history.py` | Wide history-table assembly with the existing zero padding |
| `writers.py` | Stream-based VTU, PVD, CSV, and JSON serialization |

These modules import only the standard library and NumPy. They receive plain
records, labels, and arrays; none receives an Abaqus instance or field object.
The retained coordinator still performs source queries, including Abaqus centroid
queries and section-point filtering.

Field layout uses named attributes internally. The new frame-writing path derives
field names, component metadata, and active-array attributes from `FieldArray`
records instead of maintaining XML buffers and metadata maps in parallel.
Compatibility methods on the old class delegate to the same transformations and
writers; they do not contain a second numerical implementation.

The original seven regression scenarios now exercise the extracted numerical
functions and CSV writer directly, without bypassing a constructor or stubbing
Abaqus imports. Separate coordinator tests use synthetic query results to check
the wiring that remains in `odb2vtk.py`.

## Compatibility choices

- Keep documented flags, output naming, suffix behavior, and initialization order.
- Keep existing CSV/JSON schemas and the corrected history-column placement.
- Preserve instance-scoped element mapping and explicit integration-point placement.
- Preserve Abaqus centroid results rather than calculating an average locally.
- Preserve current section-point naming and orientation conventions, including
  optional orientation when stress is absent and zero directions for missing data.
- Preserve existing VTU numeric declarations, XML version strings, and active-array
  attribute conventions. Fixing those conventions is a separate behavior change.
- Keep source ownership, exception policy, and process exit behavior for later phases.
- Use named tuples and conservative production syntax rather than requiring new
  language features or adding runtime dependencies.

Only numerical/metadata equivalence is required for XML output. Text whitespace
and progress messages may differ.

## Automated checks

Run from the repository root with Python and NumPy installed:

```text
python -m unittest discover -s python/tests -v
```

Or use the Abaqus interpreter:

```text
abaqus python -m unittest discover -s python/tests -v
```

Both runs passed all 21 tests. The checks cover:

- Independent imports while actively blocking Abaqus-specific imports.
- Shared labels across instances, noncontiguous labels, and mesh connectivity.
- Existing element families, nodal placement, integration-point ordering, mixed
  block sizes, missing-point padding, and multiple components.
- Quaternion orientation conversion, section-point splitting, and preservation
  of supplied centroid results.
- Scalar component metadata, field attributes, PVD references, CSV formatting,
  history-column regressions, and header schema.
- Retained coordinator calls, selected instances, suffixes, and missing stress.

Local environments used:

| Environment | Python | NumPy |
| --- | --- | --- |
| Ordinary Python | 3.12.14 | 2.3.5 |
| Abaqus 2025 | 3.10.5 | 1.22.4 |

Black formatting checks passed for all Python files, and `git diff --check`
passed. The default parallel Black runner stalled under the Windows sandbox;
the final check used Black's per-file formatting interface in one process.

The existing Python CI workflow runs the expanded test discovery command without
requiring Abaqus. GitHub-hosted CI itself has not been run locally.

## Real ODB comparisons

Before extraction, a snapshot of the exporter containing the two recent bug
fixes was saved outside the repository. The bundled `Job-1.odb` and
`2d_planar.odb` were upgraded into temporary copies using Abaqus 2025. Original
repository fixtures were preserved.

The snapshot and refactored exporter each exported both frames from `Step-1`:

| Fixture | Selected instance | Frames |
| --- | --- | --- |
| `Job-1.odb` | `L-SHAPE-PART-1` | 0, 1 |
| `2d_planar.odb` | `PART-1-1` | 0, 1 |

Comparisons passed for all four VTU files: identical element structure and XML
attributes, plus numerical array agreement with `rtol=1e-12`, `atol=1e-12`.
PVD entries and header JSON matched semantically. CSV contents matched exactly
for both fixtures. The existing CLI also successfully exported the 3D fixture
with history output and a suffix.

Baseline snapshots, upgraded databases, comparison scripts, and generated
outputs were kept in a task-specific temporary directory, not committed as new
binary fixtures.

## Remaining work

Phase 2 will introduce source lifetime management and isolate the remaining
Abaqus queries. Phase 3 will replace the legacy initialization sequence with the
cohesive converter interface.

This phase does not establish a complete supported-version matrix, validate
Abaqus 2023, measure performance on a large ODB, or run a VTK/ParaView reader.
Those acceptance checks remain in the master plan. The architecture extraction
has been validated against the two compatible upgraded fixtures and synthetic
cases described above.
