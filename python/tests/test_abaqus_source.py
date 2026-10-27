"""Opt-in contract check against a real ODB under Abaqus Python."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core.source import AbaqusSource


@unittest.skipUnless(
    os.environ.get("ODB2VTK_TEST_ODB"), "Set ODB2VTK_TEST_ODB to a compatible ODB"
)
class RealAbaqusSourceTests(unittest.TestCase):
    def test_frame_revisit_preserves_native_field_values(self):
        with AbaqusSource.open(os.environ["ODB2VTK_TEST_ODB"]) as source:
            step = next((step for step in source.steps if step.frame_count > 1), None)
            if step is None:
                self.skipTest("A frame-revisit check requires at least two frames")
            instance = source.instance_names[0]
            names = source.field_names(step.name, 0)
            name = next(
                (
                    name
                    for name in names
                    if source.describe_field(
                        step.name, 0, name, [instance]
                    ).layout.position
                    == "NODAL"
                ),
                None,
            )
            if name is None:
                self.skipTest("A frame-revisit check requires a nodal field")
            first = tuple(source.field_blocks(step.name, 0, name, instance, "NODAL"))
            self.assertTrue(first)
            source.frame_time(step.name, 1)
            source.field_names(step.name, 1)
            if name in source.field_names(step.name, 1):
                tuple(source.field_blocks(step.name, 1, name, instance, "NODAL"))
            self.assertEqual(source.field_names(step.name, 0), names)
            again = tuple(source.field_blocks(step.name, 0, name, instance, "NODAL"))
            self.assertEqual(len(first), len(again))
            for original, revisited in zip(first, again):
                np.testing.assert_array_equal(original.labels, revisited.labels)
                np.testing.assert_array_equal(original.values, revisited.values)
        with self.assertRaisesRegex(RuntimeError, "source is closed"):
            source.field_names(step.name, 0)

    def test_real_source_contract_and_snapshot_lifetime(self):
        snapshots = []
        with AbaqusSource.open(os.environ["ODB2VTK_TEST_ODB"]) as source:
            instances = source.instance_names
            self.assertTrue(instances)
            step = source.steps[0]
            self.assertGreater(step.frame_count, 0)
            mesh = source.mesh(instances[0])
            labels = source.mesh_labels(instances[0])
            self.assertEqual(len(mesh.coordinates), len(labels.node_labels))
            for name in source.field_names(step.name, 0):
                info = source.describe_field(step.name, 0, name, instances)
                self.assertIsInstance(info.layout.position, str)
                for instance in instances:
                    for block in source.field_blocks(
                        step.name, 0, name, instance, info.layout.position
                    ):
                        self.assertEqual(len(block.labels), len(block.values))
                        self.assertEqual(block.values.ndim, 2)
                        self.assertNotEqual(block.values.dtype, np.dtype(object))
                        self.assertFalse(hasattr(block, "getSubset"))
                        snapshots.append((block.values, block.values.copy()))
            for block in source.orientation_blocks(step.name, 0, instances):
                self.assertEqual(len(block.labels), len(block.quaternions))
                snapshots.append((block.quaternions, block.quaternions.copy()))
            for series in source.history(step.name):
                self.assertEqual(len(series.timestamps), len(series.values))
                snapshots.append((series.values, series.values.copy()))
        self.assertTrue(source.closed)
        self.assertTrue(snapshots)
        for values, expected in snapshots:
            np.testing.assert_array_equal(values, expected)
        with self.assertRaisesRegex(RuntimeError, "source is closed"):
            source.frame_time(step.name, 0)


if __name__ == "__main__":
    unittest.main()
