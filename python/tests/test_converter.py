"""Request-level export behavior, streaming, and per-file publication failures."""

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk import ODB2VTK
from odb2vtk_core import Converter, OutputOptions, Selection
from odb2vtk_core import writers
from odb2vtk_core.errors import ExportFailure, OutputError, SelectionError, SourceError
from odb2vtk_core.models import FieldLayout, HistorySeries, StepInfo
from support import make_source


class SourceSpy:
    """Observe queries through the source interface without inspecting a converter."""

    def __init__(self, source):
        self.source = source
        self.mesh_reads = []
        self.label_reads = []
        self.events = []
        self.fail_step = None
        self.fail_frame = None

    def __getattr__(self, name):
        return getattr(self.source, name)

    def mesh(self, instance):
        self.mesh_reads.append(instance)
        return self.source.mesh(instance)

    def mesh_labels(self, instance):
        self.label_reads.append(instance)
        return self.source.mesh_labels(instance)

    def field_blocks(self, step, frame, name, instance, position, section=None):
        self.events.append(("read", name))
        if (step, frame) == (self.fail_step, self.fail_frame):
            raise RuntimeError("source read failed")
        return self.source.field_blocks(step, frame, name, instance, position, section)


def two_frame_source():
    source = make_source()
    source._times["Step-1"] = (0.5, 1.0)
    source._layouts[("Step-1", 1)] = source._layouts[("Step-1", 0)]
    for name in source.field_names("Step-1", 0):
        source._blocks[("Step-1", 1, name)] = source._blocks[("Step-1", 0, name)]
    source._orientations[("Step-1", 1)] = source._orientations[("Step-1", 0)]
    return source


class SelectionTests(unittest.TestCase):
    def test_selection_copies_inputs_and_preserves_explicit_order(self):
        instances = ["B", "A"]
        frames = [1, 0]
        steps = {"Step-1": frames}
        selection = Selection(instances, steps)
        instances.clear()
        frames.clear()
        steps.clear()
        self.assertEqual(selection.instances, ("B", "A"))
        self.assertEqual(selection.steps, (("Step-1", (1, 0)),))
        with self.assertRaises(AttributeError):
            selection.instances = ("A",)

    def test_bad_selections_are_rejected(self):
        for instances, steps in (
            ("A", {"Step-1": [0]}),
            (["A", "A"], {"Step-1": [0]}),
            ([""], {"Step-1": [0]}),
            (["A"], {}),
            (["A"], {"": [0]}),
            (["A"], {"Step-1": [-1]}),
            (["A"], {"Step-1": [True]}),
            (["A"], {"Step-1": [0.0]}),
            (["A"], {"Step-1": "0"}),
            (["A"], {"Step-1": [0, 0]}),
            (["A"], [("Step-1", [0]), ("Step-1", [1])]),
        ):
            with self.subTest(instances=instances, steps=steps):
                with self.assertRaises(SelectionError):
                    Selection(instances, steps)

    def test_output_options_are_immutable_and_keep_legacy_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            output = OutputOptions.from_odb(Path(directory) / "job.v1.odb", "_case")
            self.assertEqual(output.data_directory, os.path.join(directory, "job_case"))
            self.assertEqual(
                output.header_path, os.path.join(directory, "job_case.json")
            )
            self.assertEqual(
                output.frame_path("Step-1", 2),
                os.path.join(directory, "job_case", "Step-1_2.vtu"),
            )
            with self.assertRaises(AttributeError):
                output.name = "different"

    def test_output_names_cannot_escape_the_selected_directory(self):
        for name, suffix in (
            ("../escape", ""),
            ("job", "/escape"),
            ("..", ""),
            ("NUL", ""),
            ("job", "."),
        ):
            with self.subTest(name=name, suffix=suffix):
                with self.assertRaises(OutputError):
                    OutputOptions(".", name, suffix)
        with self.assertRaises(OutputError):
            OutputOptions("invalid\x00directory", "job")


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = SourceSpy(two_frame_source())
        self.addCleanup(self.source.close)
        self.converter = Converter(self.source)
        self.outputs = OutputOptions(self.directory.name, "job", "_case")
        self.selection = Selection(["A", "B"], {"Step-1": [0, 1]})

    def test_inspection_returns_metadata_without_writing_files(self):
        metadata = self.converter.inspect()
        self.assertEqual(
            metadata,
            {
                "instances": ["A", "B"],
                "steps": [["Step-1", ["Step-1-frame-0", "Step-1-frame-1"]]],
            },
        )
        self.assertEqual(os.listdir(self.directory.name), [])
        self.assertEqual(self.source.mesh_reads, [])

    def test_closed_source_fails_before_output_creation(self):
        self.source.close()
        with self.assertRaises(SourceError):
            self.converter.export_frames(self.selection, self.outputs)
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_failed_source_metadata_is_reported_before_conversion(self):
        class UnreadableMetadata(SourceSpy):
            @property
            def steps(self):
                raise OSError("metadata unavailable")

        source = UnreadableMetadata(self.source.source)
        with self.assertRaisesRegex(SourceError, "metadata unavailable"):
            Converter(source).export_frames(self.selection, self.outputs)
        self.assertEqual(source.mesh_reads, [])
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_colliding_paths_are_rejected_before_mesh_reads(self):
        self.source.source._times["step-1"] = (0.5,)
        selection = Selection(["A"], [("Step-1", [0]), ("step-1", [0])])
        with patch(
            "odb2vtk_core.outputs.os.path.normcase",
            side_effect=lambda path: path.lower(),
        ):
            with self.assertRaisesRegex(OutputError, "collide"):
                self.converter.export_frames(selection, self.outputs)
        self.assertEqual(self.source.mesh_reads, [])
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_collection_can_be_disabled_explicitly(self):
        outputs = OutputOptions(self.directory.name, "job", write_pvd=False)
        result = self.converter.export_frames(self.selection, outputs)
        self.assertEqual(len(result.paths), 2)
        self.assertFalse(os.path.exists(outputs.collection_path))

    def test_unsupported_fields_are_reported_without_changing_position_support(self):
        source = self.source.source
        source._layouts[("Step-1", 0)]["DIRECT"] = FieldLayout(
            "Scalars", ("0",), "CENTROID"
        )
        source._blocks[("Step-1", 0, "DIRECT")] = []
        result = self.converter.export_frames(
            Selection(["A"], {"Step-1": [0]}), self.outputs
        )
        self.assertEqual(
            [(item.field, item.message) for item in result.diagnostics],
            [("DIRECT", "Unsupported field position: CENTROID")],
        )
        names = [
            array.attrib["Name"]
            for array in ET.parse(result.frames[0].path).findall(
                "UnstructuredGrid/Piece/CellData/DataArray"
            )
        ]
        self.assertNotIn("DIRECT", names)

    def test_export_needs_no_initialization_and_builds_mesh_once_per_request(self):
        events = []
        converter = Converter(self.source, progress=events.append)
        with contextlib.redirect_stdout(io.StringIO()) as console:
            result = converter.export_frames(self.selection, self.outputs)
        self.assertEqual(console.getvalue(), "")
        self.assertEqual(self.source.mesh_reads, ["A", "B"])
        self.assertEqual(self.source.label_reads, ["A", "B"])
        self.assertEqual(len(result.paths), 3)
        self.assertEqual(
            [(frame.step, frame.frame, frame.timestep) for frame in result.frames],
            [("Step-1", 0, 0.5), ("Step-1", 1, 1.0)],
        )
        self.assertTrue(all(os.path.isfile(path) for path in result.paths))
        entries = ET.parse(self.outputs.collection_path).findall("Collection/DataSet")
        self.assertEqual(
            [entry.attrib["file"] for entry in entries],
            ["Step-1_0.vtu", "Step-1_1.vtu"],
        )
        self.assertEqual(
            [event.kind for event in events],
            ["frame_completed", "frame_completed", "collection_completed"],
        )
        self.assertEqual([event.completed for event in events], [1, 2, 2])
        self.assertFalse(self.source.closed)

    def test_subsequent_selection_cannot_reuse_stale_indices(self):
        self.converter.export_frames(Selection(["A"], {"Step-1": [0]}), self.outputs)
        result = self.converter.export_frames(
            Selection(["B"], {"Step-1": [0]}), self.outputs
        )
        piece = ET.parse(result.frames[0].path).find("UnstructuredGrid/Piece")
        self.assertEqual(piece.attrib, {"NumberOfPoints": "4", "NumberOfCells": "1"})
        coordinates = np.fromstring(
            piece.find("Points/DataArray").text, sep=" "
        ).reshape((-1, 3))
        np.testing.assert_array_equal(coordinates[:, 1], [100] * 4)
        self.assertEqual(self.source.mesh_reads, ["A", "B"])

    def test_invalid_requests_fail_before_mesh_reads_or_output_creation(self):
        for selection in (
            Selection(["UNKNOWN"], {"Step-1": [0]}),
            Selection(["A"], {"UNKNOWN": [0]}),
            Selection(["A"], {"Step-1": [2]}),
            Selection([], {"Step-1": [0]}),
            Selection(["A"], {"Step-1": []}),
        ):
            with self.subTest(selection=selection):
                with self.assertRaises(SelectionError):
                    self.converter.export_frames(selection, self.outputs)
        self.assertEqual(self.source.mesh_reads, [])
        self.assertEqual(os.listdir(self.directory.name), [])

    def test_invalid_output_target_fails_before_mesh_reads(self):
        Path(self.outputs.data_directory).write_text("existing file")
        with self.assertRaises(OutputError):
            self.converter.export_frames(self.selection, self.outputs)
        self.assertEqual(self.source.mesh_reads, [])

    def test_history_only_selection_does_not_require_mesh_or_instances(self):
        result = self.converter.export_history(
            Selection([], {"Step-1": []}), self.outputs
        )
        self.assertEqual(result.paths, (self.outputs.history_path,))
        self.assertEqual(result.frames, ())
        self.assertEqual(self.source.mesh_reads, [])
        self.assertEqual(self.source.label_reads, [])
        self.assertEqual(
            Path(result.paths[0]).read_text().splitlines()[1:],
            ["11.000000,21.000000", "12.000000,22.000000"],
        )

    def test_history_can_use_a_source_that_has_no_mesh_interface(self):
        history_source = types.SimpleNamespace(
            closed=False,
            steps=(StepInfo("History", 0),),
            history=lambda step: iter([HistorySeries("energy", [0.0], [42.0])]),
        )
        result = Converter(history_source).export_history(
            Selection([], {"History": []}), self.outputs
        )
        self.assertIn("42.000000", Path(result.paths[0]).read_text())

    def test_fields_are_written_before_the_next_numerical_field_is_read(self):
        original = writers.write_data_array

        def record_write(stream, field):
            self.source.events.append(("write", field.name))
            original(stream, field)

        with patch.object(writers, "write_data_array", side_effect=record_write):
            self.converter.export_frames(
                Selection(["A"], {"Step-1": [0]}), self.outputs
            )
        events = self.source.events
        self.assertLess(events.index(("write", "U")), events.index(("read", "TEMP")))
        self.assertLess(events.index(("write", "TEMP")), events.index(("read", "S")))

    def test_failure_preserves_existing_files_and_reports_only_published_frames(self):
        os.makedirs(self.outputs.data_directory)
        old_frame = self.outputs.frame_path("Step-1", 1)
        Path(old_frame).write_text("previous frame")
        Path(self.outputs.collection_path).write_text("previous collection")
        self.source.fail_step, self.source.fail_frame = "Step-1", 1
        with self.assertRaises(ExportFailure) as failure:
            self.converter.export_frames(self.selection, self.outputs)
        result = failure.exception.result
        self.assertEqual(result.paths, (self.outputs.frame_path("Step-1", 0),))
        self.assertEqual([frame.frame for frame in result.frames], [0])
        self.assertIsInstance(failure.exception.cause, RuntimeError)
        self.assertEqual(Path(old_frame).read_text(), "previous frame")
        self.assertEqual(
            Path(self.outputs.collection_path).read_text(), "previous collection"
        )
        self.assertFalse(
            any(
                name.endswith(".tmp")
                for name in os.listdir(self.outputs.data_directory)
            )
        )

    def test_failed_serialization_leaves_no_completed_file_or_collection(self):
        def fail(stream, field):
            stream.write("partial field")
            raise ValueError("serializer failed")

        with patch.object(writers, "write_data_array", side_effect=fail):
            with self.assertRaises(ExportFailure) as failure:
                self.converter.export_frames(self.selection, self.outputs)
        self.assertEqual(failure.exception.result.paths, ())
        self.assertEqual(os.listdir(self.outputs.data_directory), [])

    def test_failed_collection_publication_tracks_all_completed_frames(self):
        with patch.object(
            writers, "write_pvd", side_effect=ValueError("collection failed")
        ):
            with self.assertRaises(ExportFailure) as failure:
                self.converter.export_frames(self.selection, self.outputs)
        self.assertEqual(len(failure.exception.result.frames), 2)
        self.assertEqual(len(failure.exception.result.paths), 2)
        self.assertFalse(os.path.exists(self.outputs.collection_path))
        self.assertFalse(
            any(
                name.endswith(".tmp")
                for name in os.listdir(self.outputs.data_directory)
            )
        )

    def test_failed_replacement_preserves_the_existing_destination(self):
        os.makedirs(self.outputs.data_directory)
        target = self.outputs.frame_path("Step-1", 0)
        Path(target).write_text("existing frame")
        with patch(
            "odb2vtk_core.outputs.os.replace",
            side_effect=PermissionError("locked destination"),
        ):
            with self.assertRaises(ExportFailure) as failure:
                self.converter.export_frames(
                    Selection(["A"], {"Step-1": [0]}), self.outputs
                )
        self.assertIsInstance(failure.exception.cause, OutputError)
        self.assertEqual(Path(target).read_text(), "existing frame")
        self.assertEqual(failure.exception.result.paths, ())
        self.assertEqual(os.listdir(self.outputs.data_directory), ["Step-1_0.vtu"])

    def test_history_and_header_failures_preserve_existing_files(self):
        for writer, method, target in (
            (
                "write_csv",
                lambda: self.converter.export_history(self.selection, self.outputs),
                self.outputs.history_path,
            ),
            (
                "write_header",
                lambda: self.converter.export_header(self.outputs),
                self.outputs.header_path,
            ),
        ):
            with self.subTest(writer=writer):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                Path(target).write_text("previous output")
                with patch.object(
                    writers, writer, side_effect=ValueError("formatting failed")
                ):
                    with self.assertRaises(ExportFailure) as failure:
                        method()
                self.assertEqual(failure.exception.result.paths, ())
                self.assertEqual(Path(target).read_text(), "previous output")
                self.assertFalse(
                    any(
                        path.name.endswith(".tmp")
                        for path in Path(self.directory.name).rglob("*")
                    )
                )

    def test_progress_callback_failure_still_reports_the_file_already_published(self):
        def fail(event):
            self.assertTrue(os.path.isfile(event.path))
            raise ValueError("progress callback failed")

        with self.assertRaises(ExportFailure) as failure:
            Converter(self.source, progress=fail).export_frames(
                self.selection, self.outputs
            )
        self.assertEqual(len(failure.exception.result.frames), 1)
        self.assertTrue(os.path.isfile(failure.exception.result.paths[0]))
        self.assertFalse(os.path.exists(self.outputs.collection_path))

    def test_legacy_selection_copies_inputs_and_reselection_prepares_new_mesh(self):
        facade = ODB2VTK(
            os.path.join(self.directory.name, "job.odb"), "", source=self.source
        )
        instances, frames = ["A"], [0]
        facade.ReadArgs(instances, {"Step-1": frames})
        facade.ConstructMap()
        instances[:] = ["B"]
        frames[:] = [99]
        with contextlib.redirect_stdout(io.StringIO()):
            result = facade.WriteVTUFiles()
        points = ET.parse(result.frames[0].path).find(
            "UnstructuredGrid/Piece/Points/DataArray"
        )
        np.testing.assert_array_equal(
            np.fromstring(points.text, sep=" ").reshape((-1, 3))[:, 1], [0] * 4
        )
        facade.ReadArgs(["B"], {"Step-1": [0]})
        with contextlib.redirect_stdout(io.StringIO()):
            result = facade.WriteVTUFiles()
        field = ET.parse(result.frames[0].path).find(
            'UnstructuredGrid/Piece/PointData/DataArray[@Name="TEMP"]'
        )
        np.testing.assert_array_equal(
            np.fromstring(field.text, sep=" "),
            [103, 101, 104, 102],
        )


if __name__ == "__main__":
    unittest.main()
