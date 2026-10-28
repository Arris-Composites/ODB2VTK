"""Vectorized mapping semantics, range bounds, and placement error behavior."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core.fields import LabelLookup, place_cell_data, place_point_data


class LabelLookupTests(unittest.TestCase):
    def test_compact_unsorted_labels_preserve_output_rows_and_repetitions(self):
        mapping = {30: 8, 28: 3, 29: 6}
        lookup = LabelLookup(mapping)
        result = lookup.indices([29, 30, 28, 29])
        np.testing.assert_array_equal(result, [6, 8, 3, 6])
        self.assertEqual(result.dtype, np.dtype(np.intp))
        self.assertEqual(lookup.nbytes, 3 * np.dtype(np.intp).itemsize)

    def test_sparse_labels_use_storage_proportional_to_label_count(self):
        mapping = {-1000000: 3, 2000000: 0, 20: 7}
        lookup = LabelLookup(mapping)
        np.testing.assert_array_equal(
            lookup.indices([20, -1000000, 2000000]), [7, 3, 0]
        )
        self.assertEqual(lookup.nbytes, len(mapping) * (8 + np.dtype(np.intp).itemsize))

    def test_compact_ranges_can_have_large_positive_or_negative_offsets(self):
        for start in (-(2**63), 2**63 - 4, 10**12):
            with self.subTest(start=start):
                lookup = LabelLookup({start: 7, start + 2: 4})
                np.testing.assert_array_equal(
                    lookup.indices([start + 2, start]), [4, 7]
                )
                self.assertEqual(lookup.nbytes, 3 * np.dtype(np.intp).itemsize)

    def test_first_missing_label_is_reported_for_holes_and_range_misses(self):
        for mapping, labels, missing in (
            ({10: 0, 12: 1}, [11, 100], 11),
            ({10: 0, 12: 1}, [-100, 11], -100),
            ({-1000000: 0, 2000000: 1}, [0, 3000000], 0),
            ({-1000000: 0, 2000000: 1}, [3000000, 0], 3000000),
        ):
            with self.subTest(mapping=mapping, labels=labels):
                with self.assertRaises(KeyError) as error:
                    LabelLookup(mapping).indices(labels)
                self.assertEqual(error.exception.args, (missing,))

    def test_unsigned_labels_do_not_wrap_or_hide_an_earlier_missing_label(self):
        lookup = LabelLookup({0: 3, 2: 4})
        np.testing.assert_array_equal(
            lookup.indices(np.array([2, 0], dtype=np.uint64)), [4, 3]
        )
        for labels, missing in (([1, 2**63], 1), ([2, 2**63], 2**63)):
            with self.subTest(labels=labels):
                with self.assertRaises(KeyError) as error:
                    lookup.indices(np.array(labels, dtype=np.uint64))
                self.assertEqual(error.exception.args, (missing,))

    def test_empty_lookup_and_empty_inputs(self):
        empty = LabelLookup({})
        self.assertEqual(empty.nbytes, 0)
        self.assertEqual(empty.indices([]).shape, (0,))
        self.assertEqual(LabelLookup({1: 0}).indices([]).shape, (0,))
        with self.assertRaises(KeyError) as error:
            empty.indices([9])
        self.assertEqual(error.exception.args, (9,))

    def test_lookup_owns_mapping_and_returned_indices_do_not_modify_it(self):
        for mapping in ({1: 4, 2: 7}, {1: 4, 1000000: 7}):
            with self.subTest(mapping=mapping):
                labels = list(mapping)
                expected = list(mapping.values())
                lookup = LabelLookup(mapping)
                mapping.clear()
                lookup.indices(labels).fill(99)
                np.testing.assert_array_equal(lookup.indices(labels), expected)

    def test_noninteger_or_multidimensional_labels_are_not_silently_coerced(self):
        lookup = LabelLookup({1: 0})
        for labels in ([1.5], ["1"], np.array([True])):
            with self.subTest(labels=labels):
                with self.assertRaises(TypeError):
                    lookup.indices(labels)
        with self.assertRaises(ValueError):
            lookup.indices([[1]])
        with self.assertRaises(TypeError):
            LabelLookup({1.5: 0})
        with self.assertRaises(TypeError):
            LabelLookup({1: 1.5})
        with self.assertRaises(ValueError):
            LabelLookup({1: -1})

    def test_instance_lookups_do_not_share_overlapping_labels(self):
        output = np.zeros((4, 1))
        place_point_data([10], [[11]], LabelLookup({10: 0}), output)
        place_point_data([10], [[22]], LabelLookup({10: 3}), output)
        np.testing.assert_array_equal(output[:, 0], [11, 0, 0, 22])

    def test_unknown_labels_leave_point_and_cell_outputs_unchanged(self):
        for mapping in ({1: 0, 3: 1}, {1: 0, 1000000: 1}):
            for cell in (False, True):
                with self.subTest(mapping=mapping, cell=cell):
                    output = np.full((2, 2), 99.0)
                    with self.assertRaises(KeyError):
                        if cell:
                            place_cell_data(
                                [1, 2], [[1], [2]], [1, 2], LabelLookup(mapping), output
                            )
                        else:
                            place_point_data(
                                [1, 2], [[1, 2], [3, 4]], LabelLookup(mapping), output
                            )
                    np.testing.assert_array_equal(output, np.full((2, 2), 99.0))

    def test_dense_and_sparse_placement_match_dictionary_reference(self):
        for labels in ([8, 2, 6, 4], [-2000000, 7000000, 10, 30000000]):
            mapping = {label: row for row, label in enumerate(labels)}
            requested = np.array(
                [labels[2], labels[0], labels[3], labels[1], labels[2]]
            )
            values = np.arange(15).reshape(5, 3)
            expected = np.zeros((4, 3))
            expected[[mapping[label] for label in requested]] = values
            output = np.zeros_like(expected)
            place_point_data(requested, values, LabelLookup(mapping), output)
            np.testing.assert_array_equal(output, expected)

    def test_dense_and_sparse_integration_points_keep_component_slices_and_padding(
        self,
    ):
        for low, high in ((6, 8), (10, 1000000)):
            with self.subTest(low=low, high=high):
                output = np.zeros((3, 6))
                place_cell_data(
                    [high, low, high, low],
                    np.array([[202, 1202], [101, 1101], [201, 1201], [103, 1103]]),
                    [2, 1, 1, 3],
                    LabelLookup({high: 2, low: 0}),
                    output,
                )
                np.testing.assert_array_equal(
                    output,
                    [
                        [101, 1101, 0, 0, 103, 1103],
                        [0, 0, 0, 0, 0, 0],
                        [201, 1201, 202, 1202, 0, 0],
                    ],
                )


if __name__ == "__main__":
    unittest.main()
