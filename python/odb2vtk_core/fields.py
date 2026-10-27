"""Place numerical field values into output order without Abaqus dependencies."""

import numpy as np


def place_point_data(labels, values, label_map, output):
    """Fill and return a caller-owned array, preserving unfilled entries."""
    indices = [label_map[label] for label in labels]
    output[indices] = values
    return output


def place_cell_data(labels, values, integration_points, label_map, output):
    """Map rows by element identity and optional one-based integration point.

    Each integration-point row occupies its own component slice. Input rows may
    be interleaved; missing points retain the caller's existing padding.
    """
    if integration_points is None:
        return place_point_data(labels, values, label_map, output)
    indices = np.array([label_map[label] for label in labels], dtype=int)
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
