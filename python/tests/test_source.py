"""Shared source contracts and ownership tests without Abaqus import stubs."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk import ODB2VTK
from odb2vtk_core.models import SectionPoint
from odb2vtk_core.source import AbaqusSource, ReadableOdb
from odb2vtk_core.errors import SelectionError
from support import CONSTANTS, NativeOdb, make_source


class SourceContract:
    def setUp(self):
        self.source, self.handle = self.make_subject()
        self.addCleanup(self.source.close)

    def test_metadata_and_mesh_preserve_instance_identity_and_order(self):
        self.assertEqual(self.source.instance_names, ("A", "B"))
        self.assertEqual(
            [(step.name, step.frame_count) for step in self.source.steps],
            [("Step-1", 1)],
        )
        self.assertEqual(self.source.frame_time("Step-1", 0), 0.5)
        self.assertEqual(self.source.mesh_labels("A").node_labels, (3, 1, 4, 2))
        self.assertEqual(self.source.mesh_labels("B").element_labels, (7,))
        mesh = self.source.mesh("B")
        self.assertEqual(mesh.coordinates[0], (3, 100, 0))
        self.assertEqual(mesh.elements[0].connectivity, (1, 2, 3, 4))

    def test_field_metadata_and_sections_are_plain_records(self):
        self.assertEqual(self.source.field_names("Step-1", 0), ("U", "TEMP", "S"))
        info = self.source.describe_field("Step-1", 0, "S", ["A", "B"])
        self.assertEqual(info.layout.position, "INTEGRATION_POINT")
        self.assertEqual(info.layout.component_names, ("S11", "S22"))
        self.assertEqual(
            info.section_points, (SectionPoint(1, "Top"), SectionPoint(2, "Bottom"))
        )
        self.assertEqual(info.max_integration_point, 2)
        scalar = self.source.describe_field("Step-1", 0, "TEMP", ["A"])
        self.assertEqual(scalar.layout.component_names, ("0",))

    def test_field_subset_and_centroid_values_are_preserved(self):
        info = self.source.describe_field("Step-1", 0, "S", ["A", "B"])
        (block,) = self.source.field_blocks(
            "Step-1", 0, "S", "B", "CENTROID", info.section_points[0]
        )
        self.assertEqual(block.instance_name, "B")
        self.assertEqual(block.position, "CENTROID")
        self.assertIsNone(block.integration_points)
        self.assertEqual(block.section_point, SectionPoint(1, "Top"))
        np.testing.assert_array_equal(block.labels, [7])
        np.testing.assert_array_equal(block.values, [[190, 191]])

    def test_returned_arrays_do_not_alias_the_source(self):
        (block,) = self.source.field_blocks("Step-1", 0, "U", "A", "NODAL")
        block.values.fill(-1)
        block.labels.fill(-1)
        (again,) = self.source.field_blocks("Step-1", 0, "U", "A", "NODAL")
        np.testing.assert_array_equal(again.labels, [1, 2, 3, 4])
        np.testing.assert_array_equal(again.values[:, 0], [1, 2, 3, 4])
        ip = next(self.source.field_blocks("Step-1", 0, "S", "A", "INTEGRATION_POINT"))
        ip.integration_points.fill(99)
        again = next(
            self.source.field_blocks("Step-1", 0, "S", "A", "INTEGRATION_POINT")
        )
        np.testing.assert_array_equal(again.integration_points, [1, 2])

    def test_snapshots_remain_usable_after_close(self):
        field = next(self.source.field_blocks("Step-1", 0, "U", "A", "NODAL"))
        orientation = next(self.source.orientation_blocks("Step-1", 0, ["A", "B"]))
        history = next(self.source.history("Step-1"))
        self.source.close()
        np.testing.assert_array_equal(field.labels, [1, 2, 3, 4])
        np.testing.assert_array_equal(field.values[:, 0], [1, 2, 3, 4])
        np.testing.assert_array_equal(orientation.quaternions, [[0, 0, 0, 1]])
        np.testing.assert_array_equal(history.timestamps, [0, 1])
        np.testing.assert_array_equal(history.values, [11, 12])

    def test_closed_source_rejects_queries_and_reentry(self):
        self.source.close()
        for query in (
            lambda: self.source.instance_names,
            lambda: self.source.steps,
            lambda: self.source.mesh("A"),
            lambda: self.source.mesh_labels("A"),
            lambda: self.source.frame_time("Step-1", 0),
            lambda: self.source.field_names("Step-1", 0),
            lambda: self.source.describe_field("Step-1", 0, "U", ["A"]),
            lambda: list(self.source.field_blocks("Step-1", 0, "U", "A", "NODAL")),
            lambda: list(self.source.orientation_blocks("Step-1", 0, ["A"])),
            lambda: list(self.source.history("Step-1")),
            self.source.__enter__,
        ):
            with self.subTest(query=query):
                with self.assertRaisesRegex(RuntimeError, "source is closed"):
                    query()

    def test_partly_consumed_iterators_reject_reads_after_close(self):
        factories = (
            lambda source: source.field_blocks(
                "Step-1", 0, "S", "A", "INTEGRATION_POINT"
            ),
            lambda source: source.orientation_blocks("Step-1", 0, ["A", "B"]),
            lambda source: source.history("Step-1"),
        )
        for factory in factories:
            source, _ = self.make_subject()
            self.addCleanup(source.close)
            iterator = factory(source)
            next(iterator)
            source.close()
            with self.assertRaisesRegex(RuntimeError, "source is closed"):
                next(iterator)

    def test_context_closes_once_and_preserves_the_original_exception(self):
        with self.assertRaisesRegex(ValueError, "export failed"):
            with self.source:
                raise ValueError("export failed")
        self.source.close()
        self.assertTrue(self.source.closed)
        self.assertEqual(self.handle.close_calls, 1)


class InMemorySourceContractTests(SourceContract, unittest.TestCase):
    def make_subject(self):
        source = make_source()
        return source, source


class AbaqusSourceContractTests(SourceContract, unittest.TestCase):
    def make_subject(self):
        native = NativeOdb(make_source(), invalidate_on_close=True)
        return AbaqusSource(native, CONSTANTS), native

    def test_bad_bulk_shapes_are_rejected_at_the_source(self):
        field = self.handle.steps["Step-1"].frames[0].fieldOutputs["U"]
        field.blocks[0][2].data = np.zeros((1, 3))
        with self.assertRaisesRegex(ValueError, "matching lengths"):
            list(self.source.field_blocks("Step-1", 0, "U", "A", "NODAL"))

    def test_native_compatibility_reader_borrows_the_source(self):
        reader = ReadableOdb.from_source(self.source)
        self.assertEqual(tuple(reader.getInstancesKeys), ("A", "B"))
        self.assertEqual(reader.getNodes("A")[0].label, 3)
        self.assertEqual(reader.getFrame("Step-1", 0).frameValue, 0.5)
        reader.close()
        self.assertFalse(self.source.closed)
        self.source.close()
        with self.assertRaisesRegex(RuntimeError, "source is closed"):
            reader.getNodes("A")

    def test_native_compatibility_constructor_owns_its_source(self):
        with patch.object(AbaqusSource, "open", return_value=self.source) as factory:
            with ReadableOdb("job.odb") as reader:
                self.assertEqual(reader.getNodes("A")[0].label, 3)
                self.assertFalse(self.source.closed)
        factory.assert_called_once_with("job.odb", read_only=True)
        reader.close()
        self.assertEqual(self.handle.close_calls, 1)
        with self.assertRaises(TypeError):
            ReadableOdb.from_source(None)


class ConverterOwnershipTests(unittest.TestCase):
    def test_owned_source_closes_after_success(self):
        source = make_source()
        with patch.object(AbaqusSource, "open", return_value=source) as factory:
            with ODB2VTK("job.odb", "") as converter:
                self.assertIs(converter.source, source)
                self.assertFalse(source.closed)
            factory.assert_called_once_with("job.odb")
        converter.close()
        self.assertTrue(source.closed)
        self.assertEqual(source.close_calls, 1)

    def test_source_dependency_cannot_be_reassigned(self):
        source = make_source()
        self.addCleanup(source.close)
        converter = ODB2VTK("job.odb", "", source=source)
        with self.assertRaises(AttributeError):
            converter.source = make_source()

    def test_owned_source_closes_after_export_failure(self):
        source = make_source()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(
            io.StringIO()
        ):
            with patch.object(AbaqusSource, "open", return_value=source):
                with self.assertRaises(SelectionError):
                    with ODB2VTK(os.path.join(directory, "job.odb"), "") as converter:
                        converter.ReadArgs(["UNKNOWN"], {"Step-1": [0]})
                        converter.ConstructMap()
        self.assertTrue(source.closed)
        self.assertEqual(source.close_calls, 1)

    def test_owned_source_closes_on_system_exit(self):
        source = make_source()
        with patch.object(AbaqusSource, "open", return_value=source):
            with self.assertRaises(SystemExit):
                with ODB2VTK("job.odb", ""):
                    raise SystemExit(1)
        self.assertTrue(source.closed)

    def test_injected_source_remains_caller_owned_on_success_and_failure(self):
        for fail in (False, True):
            source = make_source()
            self.addCleanup(source.close)
            try:
                with ODB2VTK("job.odb", "", source=source) as converter:
                    if fail:
                        raise ValueError("caller handles this")
            except ValueError:
                pass
            converter.close()
            self.assertFalse(source.closed)
            self.assertEqual(source.close_calls, 0)
            with source:
                self.assertEqual(source.instance_names, ("A", "B"))
            self.assertTrue(source.closed)


if __name__ == "__main__":
    unittest.main()
