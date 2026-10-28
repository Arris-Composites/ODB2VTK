"""Static mesh text reuse, bounded storage and export-lifetime cleanup."""

import io
from contextlib import nullcontext
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odb2vtk_core import Converter, OutputOptions, Selection, writers
from odb2vtk_core.errors import ExportFailure
from odb2vtk_core.models import FieldArray, MeshData
from test_converter import two_frame_source


def mesh_data():
    return MeshData(
        np.array([[0.0, -0.0, 1e-30], [float("inf"), float("nan"), 1.23456789]]),
        np.array([1, 0], dtype=np.int64),
        np.array([2], dtype=np.int64),
        np.array([3], dtype=np.int64),
    )


def render(mesh, cache=None, value=1):
    stream = io.StringIO()
    field = FieldArray(
        'U & "x"',
        "PointData",
        "Scalars",
        ("value",),
        np.full((len(mesh.points), 1), value),
    )
    writers.write_vtu(stream, mesh, [field], [], mesh_text=cache)
    return stream.getvalue()


class MeshTextTests(unittest.TestCase):
    def test_memory_and_disk_caches_match_direct_output_with_changing_fields(self):
        mesh = mesh_data()
        for limit in (1, 1024 * 1024):
            with self.subTest(limit=limit), patch.object(
                writers, "_MESH_TEXT_MEMORY_BYTES", limit
            ), writers.serialized_mesh(mesh) as cache:
                for value in (1, 9, -3):
                    self.assertEqual(
                        render(mesh, cache, value), render(mesh, value=value)
                    )

    def test_empty_mesh_cache_matches_direct_output(self):
        mesh = MeshData(
            np.empty((0, 3)),
            np.array([], dtype=int),
            np.array([], dtype=int),
            np.array([], dtype=int),
        )
        with writers.serialized_mesh(mesh) as cache:
            self.assertEqual(render(mesh, cache), render(mesh))

    def test_newline_translation_matches_for_memory_and_disk(self):
        mesh = mesh_data()
        for limit in (1, 1024 * 1024):
            with patch.object(
                writers, "_MESH_TEXT_MEMORY_BYTES", limit
            ), writers.serialized_mesh(mesh) as cache:
                results = []
                for candidate in (None, cache):
                    buffer = io.BytesIO()
                    stream = io.TextIOWrapper(buffer, newline="\r\n")
                    writers.write_vtu(stream, mesh, [], [], mesh_text=candidate)
                    stream.flush()
                    results.append(buffer.getvalue())
                self.assertEqual(*results)

    def test_cache_cannot_be_used_with_a_different_snapshot(self):
        with writers.serialized_mesh(mesh_data()) as cache:
            stream = io.StringIO()
            with self.assertRaises(ValueError):
                writers.write_vtu(stream, mesh_data(), [], [], mesh_text=cache)
            self.assertEqual(stream.getvalue(), "")

    def test_spool_closes_on_success_build_failure_and_consumer_failure(self):
        factory = tempfile.SpooledTemporaryFile
        for failure in (None, "build", "consumer"):
            opened = []

            def create(*args, **kwargs):
                stream = factory(*args, **kwargs)
                opened.append(stream)
                return stream

            with self.subTest(failure=failure), patch.object(
                writers.tempfile, "SpooledTemporaryFile", side_effect=create
            ):
                with (
                    self.assertRaisesRegex(ValueError, failure)
                    if failure is not None
                    else nullcontext()
                ):
                    with (
                        patch.object(
                            writers, "_write_points", side_effect=ValueError("build")
                        )
                        if failure == "build"
                        else nullcontext()
                    ):
                        with writers.serialized_mesh(mesh_data()):
                            if failure == "consumer":
                                raise ValueError("consumer")
            self.assertEqual(len(opened), 1)
            self.assertTrue(opened[0].closed)

    def test_single_frame_export_does_not_create_spool(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            writers.tempfile,
            "SpooledTemporaryFile",
            side_effect=AssertionError("spool"),
        ):
            result = Converter(two_frame_source()).export_frames(
                Selection(["A"], {"Step-1": [0]}), OutputOptions(directory, "single")
            )
            self.assertEqual(len(result.frames), 1)

    def test_spill_failure_closes_spool_before_publishing_any_frame(self):
        opened = []
        factory = tempfile.SpooledTemporaryFile

        def create(*args, **kwargs):
            stream = factory(*args, **kwargs)
            opened.append(stream)
            return stream

        with tempfile.TemporaryDirectory() as directory, patch.object(
            writers, "_MESH_TEXT_MEMORY_BYTES", 1
        ), patch.object(
            writers.tempfile, "SpooledTemporaryFile", side_effect=create
        ), patch.object(
            writers.tempfile, "TemporaryFile", side_effect=OSError("spill failed")
        ):
            with self.assertRaises(ExportFailure) as failure:
                Converter(two_frame_source()).export_frames(
                    Selection(["A"], {"Step-1": [0, 1]}),
                    OutputOptions(directory, "failure"),
                )
            self.assertEqual(failure.exception.result.paths, ())
            self.assertIsInstance(failure.exception.cause, OSError)
            self.assertEqual(os.listdir(directory), [])
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)

    def test_export_reuses_sections_but_new_request_formats_again(self):
        source = two_frame_source()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            writers, "_write_points", wraps=writers._write_points
        ) as points, patch.object(
            writers, "_write_cells", wraps=writers._write_cells
        ) as cells:
            converter = Converter(source)
            selection = Selection(["A"], {"Step-1": [0, 1]})
            for name in ("first", "second"):
                converter.export_frames(selection, OutputOptions(directory, name))
            self.assertEqual(points.call_count, 2)
            self.assertEqual(cells.call_count, 2)

    def test_export_failure_closes_cache_and_preserves_atomic_destination(self):
        opened = []
        factory = tempfile.SpooledTemporaryFile

        def create(*args, **kwargs):
            stream = factory(*args, **kwargs)
            opened.append(stream)
            return stream

        with tempfile.TemporaryDirectory() as directory:
            options = OutputOptions(directory, "failure")
            os.makedirs(options.data_directory)
            target = Path(options.frame_path("Step-1", 0))
            target.write_text("previous")
            with patch.object(
                writers.tempfile, "SpooledTemporaryFile", side_effect=create
            ), patch.object(writers, "write_data_array", side_effect=OSError("write")):
                with self.assertRaises(ExportFailure):
                    Converter(two_frame_source()).export_frames(
                        Selection(["A"], {"Step-1": [0, 1]}), options
                    )
            self.assertEqual(target.read_text(), "previous")
            self.assertEqual(list(Path(options.data_directory).iterdir()), [target])
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)


if __name__ == "__main__":
    unittest.main()
