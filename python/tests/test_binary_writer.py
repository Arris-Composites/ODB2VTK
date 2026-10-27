"""Appended binary layout, bounded conversion, lazy fields and publication."""

import io
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref
import xml.etree.ElementTree as ET

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from odb2vtk_core import Converter, OutputOptions, Selection, binary_writer, writers
from odb2vtk_core.errors import ExportFailure, OutputError
from odb2vtk_core.models import FieldArray, MeshData
from test_converter import SourceSpy, two_frame_source

MARKER = b'<AppendedData encoding="raw">\n_'


def unpack(data):
    header, payload = data.split(MARKER, 1)
    root = ET.fromstring(header + b"</VTKFile>")
    arrays = []
    offset = 0
    types = {"Float64": "<f8", "Float32": "<f4", "Int64": "<i8"}
    for array in root.findall(".//DataArray"):
        assert int(array.attrib["offset"]) == offset
        length = struct.unpack_from("<Q", payload, offset)[0]
        offset += 8
        values = np.frombuffer(
            payload,
            dtype=types[array.attrib["type"]],
            count=length // np.dtype(types[array.attrib["type"]]).itemsize,
            offset=offset,
        )
        arrays.append((array, values))
        offset += length
    assert payload[offset:] == b"\n</AppendedData>\n</VTKFile>"
    return root, arrays


def mesh():
    return MeshData(
        np.arange(12, dtype=np.float64).reshape(4, 3),
        np.array([3, 2, 1, 0]),
        np.array([4]),
        np.array([9]),
    )


def layout(name, width, association="PointData", kind="Vectors", labels=None):
    return SimpleNamespace(
        name=name,
        association=association,
        kind=kind,
        component_count=width,
        component_names=(
            tuple(str(i) for i in range(width)) if labels is None else labels
        ),
    )


class BinaryWriterTests(unittest.TestCase):
    def test_float64_midpoints_round_directly_to_float32(self):
        # Short decimal repr lies just below the exact binary midpoint. Binary
        # conversion must retain ties-to-even, not reproduce decimal text loss.
        middle = float.fromhex("0x1.ffffff0000000p-1")
        field = FieldArray(
            "midpoint",
            "PointData",
            "Scalars",
            ("value",),
            np.array([[middle], [-middle], [middle], [-middle]]),
        )
        stream = io.BytesIO()
        binary_writer.write_vtu(stream, mesh(), [field], [])
        _, arrays = unpack(stream.getvalue())
        np.testing.assert_array_equal(
            arrays[1][1], np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float32)
        )

    def test_headers_offsets_types_names_and_payload_values(self):
        geometry = mesh()
        name = 'U & "local" <方向>\n'
        labels = ('x & "1"', "y", "z")
        point = FieldArray(
            name, "PointData", "Vectors", labels, np.arange(12).reshape(4, 3) / 10.0
        )
        cell = FieldArray(
            "S",
            "CellData",
            "Tensors",
            tuple(str(i) for i in range(9)),
            np.arange(9).reshape(1, 9),
        )
        stream = io.BytesIO()
        binary_writer.write_vtu(stream, geometry, [point], [cell])
        root, arrays = unpack(stream.getvalue())
        self.assertEqual(root.attrib["header_type"], "UInt64")
        self.assertEqual(root.attrib["byte_order"], "LittleEndian")
        self.assertNotIn("compressor", root.attrib)
        self.assertEqual(root.find(".//PointData").attrib["Vectors"], name)
        self.assertEqual(root.find(".//CellData").attrib["Tensors"], "S")
        self.assertEqual(arrays[1][0].attrib["Name"], name)
        self.assertEqual(arrays[1][0].attrib["ComponentName0"], labels[0])
        for (_, actual), expected, dtype in zip(
            arrays,
            (
                geometry.points,
                point.values,
                cell.values,
                geometry.connectivity,
                geometry.offsets,
                geometry.cell_types,
            ),
            ("<f8", "<f4", "<f4", "<i8", "<i8", "<i8"),
        ):
            self.assertEqual(actual.dtype, np.dtype(dtype))
            np.testing.assert_array_equal(
                actual, np.asarray(expected, dtype=dtype).ravel()
            )

    def test_chunks_handle_noncontiguous_big_endian_arrays_and_special_values(self):
        geometry = mesh()
        values = np.array(
            [[0.0, -0.0, np.inf, -np.inf, np.nan, 1.234567890123]] * 4, dtype=">f8"
        )[:, ::-1]
        field = FieldArray("wide", "PointData", "Scalars", tuple("abcdef"), values)
        geometry = geometry._replace(points=geometry.points.astype(">f8")[:, ::-1])

        class Stream(io.BytesIO):
            sizes = []

            def write(self, data):
                if isinstance(data, memoryview):
                    self.sizes.append(data.nbytes)
                return super().write(data)

        stream = Stream()
        with patch.object(binary_writer, "_CHUNK_BYTES", 48):
            binary_writer.write_vtu(stream, geometry, [field], [])
        root, arrays = unpack(stream.getvalue())
        self.assertLessEqual(max(stream.sizes), 48)
        self.assertGreater(len(stream.sizes), 6)
        np.testing.assert_array_equal(arrays[0][1], geometry.points.ravel())
        expected = values.astype("<f4").ravel()
        np.testing.assert_array_equal(arrays[1][1], expected)
        np.testing.assert_array_equal(np.signbit(arrays[1][1]), np.signbit(expected))
        self.assertEqual(root.find(".//PointData").attrib, {})

    def test_empty_geometry_and_arrays_have_zero_length_blocks(self):
        geometry = MeshData(
            np.empty((0, 3)),
            np.array([], dtype=int),
            np.array([], dtype=int),
            np.array([], dtype=int),
        )
        stream = io.BytesIO()
        binary_writer.write_vtu(stream, geometry, [], [])
        _, arrays = unpack(stream.getvalue())
        self.assertEqual(len(arrays), 4)
        self.assertTrue(all(values.size == 0 for _, values in arrays))

    def test_metadata_allows_fields_to_be_released_before_next_is_created(self):
        metadata = tuple(layout(str(i), 3) for i in range(4))

        def fields():
            for info in metadata:
                field = FieldArray(
                    info.name,
                    info.association,
                    info.kind,
                    info.component_names,
                    np.full((4, 3), 3.0),
                )
                reference = weakref.ref(field.values)
                yield field
                del field
                self.assertIsNone(reference())

        stream = io.BytesIO()
        binary_writer.write_vtu(
            stream,
            mesh(),
            fields(),
            iter(()),
            point_metadata=metadata,
            cell_metadata=(),
        )
        self.assertEqual(len(unpack(stream.getvalue())[1]), 8)

    def test_field_count_identity_and_shape_must_match_metadata(self):
        info = layout("U", 3)
        correct = FieldArray(
            "U", "PointData", "Vectors", info.component_names, np.ones((4, 3))
        )
        for fields in (
            [],
            [correct, correct],
            [correct._replace(name="wrong")],
            [correct._replace(values=np.ones((3, 3)))],
            [correct._replace(values=np.ones((4, 2)))],
            [correct._replace(association="CellData")],
            [correct._replace(component_names=("wrong",) * 3)],
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                binary_writer.write_vtu(
                    io.BytesIO(),
                    mesh(),
                    fields,
                    [],
                    point_metadata=[info],
                    cell_metadata=[],
                )

    def test_offsets_can_exceed_uint32_without_allocating_large_arrays(self):
        geometry = mesh()._replace(points=range(200000000))
        stream = io.BytesIO()
        with patch.object(
            binary_writer, "_write_array", side_effect=RuntimeError("stop")
        ):
            with self.assertRaisesRegex(RuntimeError, "stop"):
                binary_writer.write_vtu(stream, geometry, [], [])
        header = stream.getvalue().split(MARKER)[0]
        root = ET.fromstring(header + b"</VTKFile>")
        self.assertEqual(
            int(root.find(".//Cells/DataArray").attrib["offset"]), 8 + 200000000 * 3 * 8
        )

    def test_invalid_format_rejected_even_after_namedtuple_replace(self):
        with self.assertRaises(OutputError):
            OutputOptions(".", "job", vtu_format="compressed")
        with tempfile.TemporaryDirectory() as directory:
            outputs = OutputOptions(directory, "job")._replace(vtu_format="invalid")
            with self.assertRaises(OutputError):
                Converter(two_frame_source()).export_frames(
                    Selection(["A"], {"Step-1": [0]}), outputs
                )
            self.assertEqual(os.listdir(directory), [])

    def test_binary_export_bypasses_ascii_cache_and_writes_pvd_and_history(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            writers.tempfile,
            "SpooledTemporaryFile",
            side_effect=AssertionError("cache"),
        ):
            outputs = OutputOptions(directory, "job", vtu_format="binary")
            converter = Converter(two_frame_source())
            result = converter.export_frames(
                Selection(["A"], {"Step-1": [0, 1]}), outputs
            )
            for frame in result.frames:
                unpack(Path(frame.path).read_bytes())
            entries = ET.parse(outputs.collection_path).findall("Collection/DataSet")
            self.assertEqual(
                [e.attrib["file"] for e in entries], ["Step-1_0.vtu", "Step-1_1.vtu"]
            )
            converter.export_history(Selection(["A"], {"Step-1": [0]}), outputs)
            self.assertTrue(Path(outputs.history_path).read_text().startswith("Step-1"))

    def test_field_failure_preserves_completed_frames_old_file_and_collection(self):
        source = SourceSpy(two_frame_source())
        source.fail_step, source.fail_frame = "Step-1", 1
        with tempfile.TemporaryDirectory() as directory:
            outputs = OutputOptions(directory, "job", vtu_format="binary")
            Path(outputs.data_directory).mkdir()
            old = Path(outputs.frame_path("Step-1", 1))
            old.write_bytes(b"previous")
            collection = Path(outputs.collection_path)
            collection.write_text("previous")
            with self.assertRaises(ExportFailure) as failure:
                Converter(source).export_frames(
                    Selection(["A"], {"Step-1": [0, 1]}), outputs
                )
            self.assertEqual(len(failure.exception.result.frames), 1)
            self.assertEqual(old.read_bytes(), b"previous")
            self.assertEqual(collection.read_text(), "previous")
            self.assertFalse(list(Path(outputs.data_directory).glob("*.tmp")))

    def test_payload_write_failure_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            outputs = OutputOptions(directory, "job", vtu_format="binary")
            Path(outputs.data_directory).mkdir()
            target = Path(outputs.frame_path("Step-1", 0))
            target.write_bytes(b"previous")

            def fail(stream, *args):
                stream.write(b"partial binary")
                raise OSError("payload failed")

            with patch.object(binary_writer, "_write_array", side_effect=fail):
                with self.assertRaises(ExportFailure) as failure:
                    Converter(two_frame_source()).export_frames(
                        Selection(["A"], {"Step-1": [0]}), outputs
                    )
            self.assertEqual(failure.exception.result.paths, ())
            self.assertEqual(target.read_bytes(), b"previous")
            self.assertEqual(list(Path(outputs.data_directory).iterdir()), [target])


if __name__ == "__main__":
    unittest.main()
