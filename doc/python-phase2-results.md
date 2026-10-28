# Python refactor: Phase 2 results

Completed: 2026-10-26.

## Implementation

- Added `AbaqusSource` in `python/odb2vtk_core/source.py`. All production imports
  of `odbAccess` and `abaqusConstants`, native subset operations, and native
  bulk-data reads now reside in this module.
- Added normalized step, section, field-description, field-block, and orientation
  records. Numerical conversion and writers continue receiving plain data.
- Added context management, idempotent closure, and clear ownership. The converter
  owns its default source; an injected source remains caller-owned. Its source
  dependency is read-only so ownership cannot drift through reassignment.
- Added resource cleanup around all existing CLI paths, including header/PVD
  exits, invalid selection, and conversion failures.
- Reduced `utilities.py` to a compatibility import. Retained native getters and
  raw-field helpers are compatibility paths, not the converter's data interface.
- Replaced the coordinator tests' import stubs with a normally constructed
  converter and an independent in-memory source.

See [the source interface](python-source-interface.md) for methods, data contracts,
ownership examples, and compatibility details.

## Lifetime and behavior

The adapter snapshots bulk arrays before returning them. Result arrays do not
alias native backing storage and remain valid after ODB closure. Iterators require
an open source; reads after closure fail explicitly. Source-side contract tests
invalidate the stand-in's backing arrays when it closes to verify this property.

Centroid extrapolation, scalar labels, section naming, orientation conventions,
source ordering, instance identity, filenames, schemas, and CLI exit behavior are
preserved for supported inputs. Missing stress is still optional. Other source
errors now propagate instead of being swallowed by the old broad orientation
exception handler. Inconsistent native row counts fail during normalization.

## Automated validation

Ordinary Python 3.12.14 with NumPy 2.3.5:

```text
python -m unittest discover -s python/tests -v
```

Result: 49 passed; the one real-ODB test was skipped because no fixture path was
configured. No Abaqus installation is required for those 49 tests.

Abaqus 2025 Python 3.10.5 with NumPy 1.22.4:

```powershell
$env:ODB2VTK_TEST_ODB = '<compatible Job-1.odb copy>'
abaqus python -m unittest discover -s python/tests -v
```

Result: all 50 tests passed. The opt-in real-source contract test also passed
separately against the compatible upgraded `2d_planar.odb` copy.

The shared contract suite runs against both the in-memory adapter and
`AbaqusSource` constructed with a native-handle stand-in. It covers metadata,
selection, section filtering, centroid values, snapshot isolation, closure,
partially consumed iterators, reentry, and exception propagation. Native-handle
stand-ins are confined to adapter tests; coordinator tests use normalized data.

CLI tests exercise successful exports, header/PVD-only paths, missing selection,
and conversion failures through the existing executable script. They verify that
owned sources close without changing the legacy exit behavior.

Black formatting and `git diff --check` passed. GitHub-hosted
CI has not been run from this session.

## Real export comparison

A snapshot of the committed Phase 1 implementation was taken before editing.
The snapshot and Phase 2 implementation exported both frames in `Step-1` for:

| Fixture | Selected instance | Frames |
| --- | --- | --- |
| Upgraded `Job-1.odb` | `L-SHAPE-PART-1` | 0, 1 |
| Upgraded `2d_planar.odb` | `PART-1-1` | 0, 1 |

All four VTU files matched in XML structure and attributes; numerical arrays
matched with `rtol=1e-12` and `atol=1e-12`. PVD references and JSON metadata matched
semantically. CSV contents matched byte for byte. The Phase 2 sources were
explicitly closed and verified closed after each export.

The original repository ODB fixtures were preserved. Upgraded copies, baseline
snapshots, generated outputs, and comparison helpers remain in task-specific
temporary directories.

## Remaining scope

Phase 3 will introduce validated selection/output options and put map construction
behind a cohesive export operation. The current explicit initialization sequence
remains supported until then.

This phase does not add field/element families, change missing-data or history
sampling policy, establish a complete Abaqus-version matrix, benchmark large ODBs,
or validate output with a VTK/ParaView reader. Those checks and enhancements remain
separate work in the master plan.
