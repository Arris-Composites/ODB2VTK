"""Place numerical field values into output order without Abaqus dependencies."""

from operator import index as integer_index

import numpy as np

_DENSE_LABEL_RATIO = 4


class LabelLookup:
    """Owned integer label-to-row lookup, bounded by selected mesh size.

    Compact ranges use an offset dense table; sparse ranges use sorted labels.
    Cached arrays are read-only. Returned index arrays are independent copies.
    """

    __slots__ = ("_labels", "_rows", "_minimum", "_maximum")

    def __init__(self, label_map):
        count = len(label_map)
        labels = np.fromiter(
            (integer_index(v) for v in label_map), dtype=np.int64, count=count
        )
        rows = np.fromiter(
            (integer_index(v) for v in label_map.values()), dtype=np.intp, count=count
        )
        if np.any(rows < 0):
            raise ValueError("Output row indices must be nonnegative")
        self._minimum = int(labels.min()) if count else 0
        self._maximum = int(labels.max()) if count else -1
        span = self._maximum - self._minimum + 1
        if count and span <= _DENSE_LABEL_RATIO * count:
            self._labels = None
            self._rows = np.full(span, -1, dtype=np.intp)
            self._rows[labels - self._minimum] = rows
        else:
            order = np.argsort(labels)
            self._labels = labels[order]
            self._labels.setflags(write=False)
            self._rows = rows[order]
        self._rows.setflags(write=False)

    @property
    def nbytes(self):
        """Bytes in cached NumPy arrays, excluding the small Python object."""
        return self._rows.nbytes + (0 if self._labels is None else self._labels.nbytes)

    def indices(self, labels):
        labels = np.asarray(labels)
        if labels.ndim != 1:
            raise ValueError("Labels must be a one-dimensional integer sequence")
        if not labels.size:
            return np.empty(0, dtype=np.intp)
        if labels.dtype.kind not in "iu":
            raise TypeError("Labels must be integers")
        if labels.dtype.kind == "u" and labels.dtype.itemsize == 8:
            overflow = labels > np.uint64(np.iinfo(np.int64).max)
            if np.any(overflow):
                first = np.flatnonzero(overflow)[0]
                # Preserve the first unknown label even if an earlier one is
                # a regular missing ID and this one is outside signed int64.
                self.indices(labels[:first].astype(np.int64))
                raise KeyError(int(labels[first]))
        labels = labels.astype(np.int64, copy=False)
        if self._labels is None:
            inside = (labels >= self._minimum) & (labels <= self._maximum)
            if np.all(inside):
                rows = self._rows[labels - self._minimum]
            else:
                rows = np.full(labels.shape, -1, dtype=np.intp)
                rows[inside] = self._rows[labels[inside] - self._minimum]
            missing = rows < 0
            if np.any(missing):
                raise KeyError(int(labels[np.flatnonzero(missing)[0]]))
            return rows
        positions = np.searchsorted(self._labels, labels)
        found = positions < len(self._labels)
        found[found] = self._labels[positions[found]] == labels[found]
        if not np.all(found):
            raise KeyError(int(labels[np.flatnonzero(~found)[0]]))
        return self._rows[positions]


def place_point_data(labels, values, label_map, output):
    """Fill and return a caller-owned array, preserving unfilled entries."""
    indices = label_map.indices(labels)
    output[indices] = values
    return output


def place_cell_data(labels, values, integration_points, label_map, output):
    """Map rows by element identity and optional one-based integration point.

    Each integration-point row occupies its own component slice. Input rows may
    be interleaved; missing points retain the caller's existing padding.
    """
    if integration_points is None:
        return place_point_data(labels, values, label_map, output)
    indices = label_map.indices(labels)
    components = values.shape[1]
    points = np.asarray(integration_points, dtype=int)
    component_indices = (points[:, None] - 1) * components + np.arange(components)
    output[indices[:, None], component_indices] = values
    return output


def quaternions_to_directions(quaternions):
    """Return the existing material 11 direction for (q1, q2, q3, q4) rows.

    q4 is the scalar term. Preserve zero quaternions as zero directions rather
    than introducing a different missing-orientation policy during extraction.
    """
    values = np.asarray(quaternions)
    q1, q2, q3, q4 = values.T
    return np.column_stack(
        (
            q4**2 + q1**2 - q2**2 - q3**2,
            2 * (q1 * q2 - q3 * q4),
            2 * (q1 * q3 + q2 * q4),
        )
    )
