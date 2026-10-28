"""Native lookup reuse, eviction, and lifetime through the public source reads."""

from collections import Counter
import copy
import os
import sys
import types
import unittest
import weakref

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core import AbaqusSource
from support import CONSTANTS, NativeOdb, make_source


class Repository(dict):
    def __init__(self, values, clone=False):
        super().__init__(values)
        self.lookups = Counter()
        self.clone = clone
        self.references = []

    def __getitem__(self, key):
        self.lookups[key] += 1
        value = super().__getitem__(key)
        if self.clone:
            value = copy.copy(value)
            self.references.append(weakref.ref(value))
        return value


class FrameHandle:
    def __init__(self, owner, index, time, fields):
        self.owner, self.index = owner, index
        self.frameValue, self.fields = time, fields

    @property
    def fieldOutputs(self):
        self.owner.repository_reads[self.index] += 1
        return self.fields


class Frames:
    def __init__(self, records):
        self.records = records
        self.lookups = Counter()
        self.repository_reads = Counter()
        self.references = []

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        self.lookups[index] += 1
        time, fields = self.records[index]
        frame = FrameHandle(self, index, time, fields)
        self.references.append(weakref.ref(frame))
        return frame


class SourceCacheTests(unittest.TestCase):
    def setUp(self):
        self.native = NativeOdb(make_source())
        second = NativeOdb(make_source())
        for field in second.steps["Step-1"].frames[0].fieldOutputs.values():
            for _, _, block in field.blocks:
                block.data = block.data * 10
        self.fields = [
            Repository(self.native.steps["Step-1"].frames[0].fieldOutputs, clone=True),
            Repository(second.steps["Step-1"].frames[0].fieldOutputs, clone=True),
        ]
        self.frames = Frames([(0.5, self.fields[0]), (1.5, self.fields[1])])
        self.other_frames = Frames([(2.5, self.fields[1])])
        self.native.steps = Repository(
            {
                "Step-1": types.SimpleNamespace(frames=self.frames),
                "Other": types.SimpleNamespace(frames=self.other_frames),
            }
        )
        self.source = AbaqusSource(self.native, CONSTANTS)
        self.addCleanup(self.source.close)

    def read_u(self, step="Step-1", frame=0):
        return next(self.source.field_blocks(step, frame, "U", "A", "NODAL"))

    def test_repeated_queries_reuse_frame_repository_and_field_handles(self):
        self.assertEqual(self.source.frame_time("Step-1", 0), 0.5)
        self.assertEqual(self.source.field_names("Step-1", 0), ("U", "TEMP", "S"))
        self.source.describe_field("Step-1", 0, "U", ["A"])
        first, second = self.read_u(), self.read_u()
        first.values.fill(-1)
        np.testing.assert_array_equal(second.values[:, 0], [1, 2, 3, 4])
        self.assertEqual(self.native.steps.lookups, {"Step-1": 1})
        self.assertEqual(self.frames.lookups, {0: 1})
        self.assertEqual(self.frames.repository_reads, {0: 1})
        self.assertEqual(self.fields[0].lookups, {"U": 1})

    def test_frame_time_reads_do_not_open_the_field_repository(self):
        self.assertEqual(self.source.frame_time("Step-1", 0), 0.5)
        self.assertEqual(self.source.frame_time("Step-1", 1), 1.5)
        self.assertEqual(self.source.frame_time("Step-1", 1), 1.5)
        self.assertEqual(self.frames.lookups, {0: 1, 1: 1})
        self.assertEqual(self.frames.repository_reads, {})

    def test_frame_and_step_switches_release_previous_handles_and_reload_on_return(
        self,
    ):
        original = self.read_u()
        old_frame = self.frames.references[-1]
        old_field = self.fields[0].references[-1]
        self.assertIsNotNone(old_frame())
        self.assertIsNotNone(old_field())
        np.testing.assert_array_equal(
            self.read_u(frame=1).values[:, 0], [10, 20, 30, 40]
        )
        self.assertIsNone(old_frame())
        self.assertIsNone(old_field())
        np.testing.assert_array_equal(
            self.read_u(step="Other").values[:, 0], [10, 20, 30, 40]
        )
        self.assertEqual(self.source.frame_time("Other", 0), 2.5)
        np.testing.assert_array_equal(self.read_u().values, original.values)
        self.assertEqual(self.frames.lookups, {0: 2, 1: 1})
        self.assertEqual(self.other_frames.lookups, {0: 1})
        self.assertEqual(self.fields[0].lookups["U"], 2)

    def test_failed_lookups_do_not_poison_later_reads_or_cache_missing_fields(self):
        self.read_u()
        for _ in range(2):
            with self.assertRaises(KeyError):
                self.source.describe_field("Step-1", 0, "MISSING", ["A"])
        self.assertEqual(self.fields[0].lookups["MISSING"], 2)
        with self.assertRaises(IndexError):
            self.source.frame_time("Step-1", 99)
        with self.assertRaises(KeyError):
            self.source.frame_time("MISSING", 0)
        np.testing.assert_array_equal(self.read_u().values[:, 0], [1, 2, 3, 4])

    def test_invalid_float_index_is_not_a_hit_for_a_cached_integer_index(self):
        self.source.frame_time("Step-1", 0)
        with self.assertRaises(TypeError):
            self.source.frame_time("Step-1", 0.0)
        self.assertEqual(self.source.frame_time("Step-1", 0), 0.5)

    def test_close_releases_warm_handles_even_when_native_close_fails(self):
        self.read_u()
        frame = self.frames.references[-1]
        field = self.fields[0].references[-1]
        original_close = self.native.close

        def fail():
            original_close()
            raise OSError("close failed")

        self.native.close = fail
        with self.assertRaisesRegex(OSError, "close failed"):
            self.source.close()
        self.assertTrue(self.source.closed)
        self.assertIsNone(frame())
        self.assertIsNone(field())
        self.source.close()
        self.assertEqual(self.native.close_calls, 1)
        for query in (
            lambda: self.source.frame_time("Step-1", 0),
            lambda: self.source.field_names("Step-1", 0),
            self.read_u,
        ):
            with self.assertRaisesRegex(RuntimeError, "source is closed"):
                query()

    def test_live_iterator_keeps_its_original_frame_after_another_frame_is_requested(
        self,
    ):
        iterator = self.source.field_blocks("Step-1", 0, "S", "A", "INTEGRATION_POINT")
        first = next(iterator)
        self.read_u(frame=1)
        second = next(iterator)
        expected = list(
            self.source.field_blocks("Step-1", 0, "S", "A", "INTEGRATION_POINT")
        )
        np.testing.assert_array_equal(first.values, expected[0].values)
        np.testing.assert_array_equal(second.values, expected[1].values)


if __name__ == "__main__":
    unittest.main()
