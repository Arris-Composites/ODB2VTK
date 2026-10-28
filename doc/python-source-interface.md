# Python source interface

The exporter consumes a source through duck typing. `AbaqusSource` supplies real
ODB data; `python/tests/support.py` supplies an independent `InMemorySource` for
ordinary Python tests. Both satisfy the contract below.

## Ownership and construction

The caller opens and owns the source; the converter borrows it:

```python
from odb2vtk_core import AbaqusSource, Converter, OutputOptions, Selection

selection = Selection(["PART-1-1"], {"Step-1": [0, 1]})
outputs = OutputOptions.from_odb(odb_path)

with AbaqusSource.open(odb_path) as source:
    converter = Converter(source)
    converter.export_frames(selection, outputs)
    # Export leaves the source open for subsequent operations.
    names = source.instance_names
# The source context closes the native ODB, including on export failure.
```

The injected dependency is exposed through the read-only `converter.source`
property. The converter does not open or close it and is not a context manager.
Use a source context or explicitly call `source.close()` in a `finally` block.
No separate map-construction call is needed.

`AbaqusSource.open(path, read_only=True)` loads Abaqus modules lazily. Importing
the package and its numerical modules works in ordinary Python with NumPy
installed. Opening a real database requires Abaqus Python.

The source constructor also accepts an already-open native ODB handle and its
constants module. This transfers ownership of that handle to the source and lets
adapter tests supply a native-handle stand-in without altering Python imports.

## Normalized reads

| Member | Result |
| --- | --- |
| `instance_names` | Tuple of names in source order |
| `steps` | Tuple of `StepInfo(name, frame_count)` records |
| `frame_time(step, frame)` | Existing frame value, without changing time semantics |
| `mesh(instance)` | `InstanceMesh(name, node_labels, coordinates, elements)` snapshot |
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

### Mesh snapshot

`mesh(instance)` reads labels and geometry together. `node_labels` is a tuple in
source order; `coordinates` is an independently owned float64 NumPy array of
shape `(len(node_labels), 3)`; `elements` contains `Element(label, connectivity,
element_type)` records. Element labels come from those records. Modifying returned
coordinates does not modify the ODB or a later read, and the snapshot survives
source closure.

`mesh_labels()` and `InstanceLabels` have been removed. Custom adapters must
include node labels in their mesh result. See the
[migration and mesh benchmark](python-mesh-snapshot-optimization.md).

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

## Current-frame handle caching

`AbaqusSource` reuses native frame/repository/field handles for the current frame.
Selecting a different step/frame evicts those handles and section metadata;
returning to a previous frame reloads it. Timestamp-only reads do not fetch
fields. All cached queries still require an open source, and closure evicts
handles before closing the native ODB, including on failure.

Numerical results remain independent copies. Native handles may retain SDK
backing buffers until eviction or closure, so source memory can include current
frame data in addition to the field currently being converted. Reopen after
external/native edits; the source assumes stable ODB data while open. See the
[cache benchmark](python-source-cache-optimization.md) for timings and memory.

## Removed compatibility access

`utilities.py`, `ReadableOdb`, and the `ODB2VTK` facade have been removed.
Native ODB handles and forwarding getters are not part of the supported
interface. Use normalized reads described above, or complete `Converter`
requests. See the [migration guide](python-architecture.md#interface-migration).
