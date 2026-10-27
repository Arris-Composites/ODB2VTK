"""Export regressions using synthetic ODB data; only NumPy is required."""

import csv
import io
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odb2vtk_core.fields import place_cell_data
from odb2vtk_core.history import assemble_history_table
from odb2vtk_core.models import HistorySeries
from odb2vtk_core.writers import write_csv


class HistoryExportTests(unittest.TestCase):
    def export_history(self, steps):
        series = [
            HistorySeries(
                step_name + "_" + region_name + "_" + output_name,
                [row[0] for row in output.data],
                [row[1] for row in output.data],
            )
            for step_name, regions in steps.items()
            for region_name, region in regions.items()
            for output_name, output in region.historyOutputs.items()
        ]
        stream = io.StringIO()
        write_csv(stream, assemble_history_table(series))
        rows = list(csv.reader(io.StringIO(stream.getvalue())))
        return rows[0], np.array(rows[1:], dtype=float)

    @staticmethod
    def region(**outputs):
        return types.SimpleNamespace(
            historyOutputs={
                name: types.SimpleNamespace(data=list(enumerate(values)))
                for name, values in outputs.items()
            }
        )

    def test_history_columns_are_preserved_across_regions(self):
        header, values = self.export_history(
            {
                "Step-1": {
                    "A": self.region(U=[11, 12]),
                    "B": self.region(U=[21, 22]),
                }
            }
        )
        self.assertEqual(header, ["Step-1_A_U", "Step-1_B_U"])
        np.testing.assert_array_equal(values, [[11, 21], [12, 22]])

    def test_history_columns_are_preserved_across_steps_and_outputs(self):
        header, values = self.export_history(
            {
                "Step-1": {"A": self.region(U=[11, 12], RF=[31])},
                "Step-2": {"A": self.region(U=[21, 22, 23])},
            }
        )
        self.assertEqual(header, ["Step-1_A_U", "Step-1_A_RF", "Step-2_A_U"])
        np.testing.assert_array_equal(values, [[11, 31, 21], [12, 0, 22], [0, 0, 23]])

    def test_single_region_history_keeps_existing_format(self):
        header, values = self.export_history(
            {"Step-1": {"A": self.region(U=[11, 12], RF=[31, 32])}}
        )
        self.assertEqual(header, ["Step-1_A_U", "Step-1_A_RF"])
        np.testing.assert_array_equal(values, [[11, 31], [12, 32]])


class IntegrationPointExportTests(unittest.TestCase):
    def setUp(self):
        self.element_maps = {"A": {20: 0, 10: 1}, "B": {20: 2}}

    def place_blocks(self, blocks, instance, values):
        for block in blocks:
            place_cell_data(
                block.elementLabels,
                block.data,
                block.integrationPoints,
                self.element_maps[instance],
                values,
            )

    @staticmethod
    def block(labels, integration_points, data):
        return types.SimpleNamespace(
            elementLabels=np.array(labels),
            integrationPoints=(
                None if integration_points is None else np.array(integration_points)
            ),
            data=np.array(data),
        )

    def test_values_follow_element_labels_instead_of_sorted_label_order(self):
        block = self.block([20, 20, 10, 10], [1, 2, 1, 2], [[201], [202], [101], [102]])
        values = np.zeros((3, 2))
        self.place_blocks([block], "A", values)
        np.testing.assert_array_equal(values, [[201, 202], [101, 102], [0, 0]])

    def test_values_follow_integration_point_numbers_and_interleaved_labels(self):
        block = self.block(
            [20, 10, 20, 10],
            [2, 1, 1, 2],
            [[202, 1202], [101, 1101], [201, 1201], [102, 1102]],
        )
        values = np.zeros((3, 4))
        self.place_blocks([block], "A", values)
        np.testing.assert_array_equal(
            values,
            [[201, 1201, 202, 1202], [101, 1101, 102, 1102], [0, 0, 0, 0]],
        )

    def test_mixed_blocks_keep_padding_and_instance_labels_separate(self):
        blocks = [
            self.block([20], [1], [[201, 1201]]),
            self.block([10, 10], [1, 3], [[101, 1101], [103, 1103]]),
        ]
        values = np.zeros((3, 6))
        self.place_blocks(blocks, "A", values)
        self.place_blocks([self.block([20], [2], [[302, 1302]])], "B", values)
        np.testing.assert_array_equal(
            values,
            [
                [201, 1201, 0, 0, 0, 0],
                [101, 1101, 0, 0, 103, 1103],
                [0, 0, 302, 1302, 0, 0],
            ],
        )

    def test_centroid_data_keeps_existing_mapping(self):
        block = self.block([10, 20], None, [[101, 1101], [201, 1201]])
        values = np.zeros((3, 2))
        self.place_blocks([block], "A", values)
        np.testing.assert_array_equal(values, [[201, 1201], [101, 1101], [0, 0]])


if __name__ == "__main__":
    unittest.main()
