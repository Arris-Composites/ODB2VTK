# Python source interface

The exporter consumes a source through duck typing. `AbaqusSource` supplies real
ODB data; `python/tests/support.py` supplies an independent `InMemorySource` for
ordinary Python tests. Both satisfy the contract below.

## Ownership and construction

Let the converter open and own the database:

```python
from odb2vtk import ODB2VTK

with ODB2VTK(odb_path, "") as converter:
    converter.ReadArgs(["PART-1-1"], {"Step-1": [0, 1]})
    converter.ConstructMap()
    converter.WriteVTUFiles()
```

Or open a source separately and lend it to the converter:

```python
from odb2vtk import ODB2VTK
from odb2vtk_core import AbaqusSource

with AbaqusSource.open(odb_path) as source:
    with ODB2VTK(odb_path, "", source=source) as converter:
        converter.ReadArgs(["PART-1-1"], {"Step-1": [0, 1]})
        converter.ConstructMap()
        converter.WriteVTUFiles()
    # The converter leaves a borrowed source open.
    names = source.instance_names
```

These examples retain the legacy facade's setup calls for compatibility.
New code can use the [converter interface](python-converter-interface.md) without
map construction. The injected dependency is exposed through the read-only
`converter.source` property. The legacy facade's `converter.close()`
closes only a source opened by the converter. A separately opened source remains
under the caller's ownership.

`AbaqusSource.open(path, read_only=True)` loads Abaqus modules lazily. Importing
the source, numerical modules, compatibility shim, or exporter works in ordinary
Python with NumPy installed. Opening a real database requires Abaqus Python.

The source constructor also accepts an already-open native ODB handle and its
constants module. This transfers ownership of that handle to the source and lets
adapter tests supply a native-handle stand-in without altering Python imports.

## Normalized reads

| Member | Result |
| --- | --- |
| `instance_names` | Tuple of names in source order |
| `steps` | Tuple of `StepInfo(name, frame_count)` records |
| `frame_time(step, frame)` | Existing frame value, without changing time semantics |
| `mesh_labels(instance)` | `InstanceLabels` with node/element labels in source order |
| `mesh(instance)` | `InstanceMesh` with coordinate tuples and `Element` records |
| `field_names(step, frame)` | Tuple of field names in source order |
| `describe_field(step, frame, name, instances)` | `FieldInfo` for the selected instances |
| `field_blocks(step, frame, name, instance, position, section=None)` | Iterator of owned `FieldBlock` records |
| `orientation_blocks(step, frame, instances)` | Iterator of owned `OrientationBlock` records |
| `history(step)` | Iterator of owned `HistorySeries` records |
| `closed`, `close()`, context management | Explicit, idempotent lifetime management |

Step and frame names/indices are explicit arguments. Field positions are strings
such as `NODAL`, `INTEGRATION_POINT`, and `CENTROID`, rather than Abaqus symbolic
constants. Native handles, instances, fields, bulk objects, and section objects
do not appear in normalized results.

### Field and orientation records

- `FieldInfo(name, layout, section_points, max_integration_point)` describes the
  existing field layout, normalized sections, and largest integration-point number.
- `FieldLayout(kind, component_names, position)` uses the existing
  Scalars/Vectors/Tensors classification and a normalized position string.
- `SectionPoint(number, description)` retains numeric identity separately from
  its display description. Existing description-based grouping remains unchanged;
  distinguishing overlapping section categories is a separate enhancement.
- `FieldBlock(instance_name, position, labels, values, integration_points,
  section_point)` contains one-dimensional labels, a two-dimensional value array,
  and optional integration-point numbers with one entry per value row.
- `OrientationBlock(instance_name, labels, quaternions)` contains the existing
  scalar-last quaternion representation. Unavailable orientation is omitted; the
  converter retains its existing zero-padding behavior.

Rows keep source order. Integration-point numbers remain one-based and are not
sorted or renumbered. The instance name remains part of node/element identity.
Centroid reads request Abaqus extrapolation through `getSubset`; the source does
not replace the returned values with an arithmetic average.

History series retain their timestamps and values. CSV assembly continues using
the existing column layout and zero padding.

## Array lifetime and errors

Each returned field, orientation, and history record has independently owned array
storage. Mutating a result does not modify the ODB or later reads. Completed reads
remain usable after closure. The adapter copies one block or history series at a
time and does not preload every frame.

Iterators must be consumed while the source is open. Queries, reentry, and reads
from partially consumed iterators after closure raise `RuntimeError`. Closing
twice is harmless. Context management closes the source and propagates exceptions.

Missing stress leaves material orientation optional. Other source/query failures
propagate rather than being silently treated as missing stress. Inconsistent
bulk-data row counts fail at the source with `ValueError`.

## Legacy access

`utilities.ReadableOdb` re-exports the compatibility class from `source.py`. Its
legacy getters retain native return types; their resource lifetime follows the
underlying source. The normal export path does not call these getters.

`converter.odb` provides this compatibility view for an `AbaqusSource`. It is not
part of the normalized interface and is unavailable for an in-memory source.
Use `converter.close()` or the source's context manager for resource management.

Old raw-field and raw-bulk helper methods remain as delegating compatibility
methods. They normalize data inside `source.py` before passing numerical arrays
to conversion functions. The old field-layout helper retains its native position
token for callers that already use Abaqus constants.
