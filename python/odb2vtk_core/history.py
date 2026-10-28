"""Build the existing wide history table from plain history series."""

import numpy as np

from .models import HistoryTable


def assemble_history_table(series):
    """Keep one column per series, original ordering, and zero row padding.

    Timestamps remain available in HistorySeries. Aligning series by timestamp
    or changing the CSV schema is outside this extraction.
    """
    series = list(series)
    rows = max([len(item.values) for item in series] or [0])
    values = np.zeros((rows, len(series)))
    for column, item in enumerate(series):
        values[: len(item.values), column] = item.values
    return HistoryTable(tuple(item.name for item in series), values)
