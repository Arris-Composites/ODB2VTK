"""Strict numerical comparison of C++ probe and Python pre-storage references."""

import argparse
import json
from pathlib import Path
import numpy as np


def values(record):
    return np.asarray(record["values"], dtype=float).reshape(record["shape"])


def compare(reference, candidate):
    assert len(reference["frames"]) == len(candidate["frames"])
    fields = 0
    for left, right in zip(reference["frames"], candidate["frames"]):
        assert (left["step"], left["frame"], left["time"]) == (
            right["step"],
            right["frame"],
            right["time"],
        )
        np.testing.assert_array_equal(values(left["points"]), values(right["points"]))
        for name in ("connectivity", "offsets", "cell_types"):
            np.testing.assert_array_equal(left[name], right[name])
        assert len(left["fields"]) == len(right["fields"])
        for a, b in zip(left["fields"], right["fields"]):
            assert (a["name"], a["association"], a["components"]) == (
                b["name"],
                b["association"],
                b["components"],
            )
            np.testing.assert_array_equal(values(a["values"]), values(b["values"]))
            fields += 1
    assert reference["history"]["headers"] == candidate["history"]["headers"]
    np.testing.assert_array_equal(
        values(reference["history"]["values"]), values(candidate["history"]["values"])
    )
    assert candidate["closed"] is True
    retained = values(candidate["retained_mesh"])
    assert retained.shape[1] == 3
    return dict(
        passed=True,
        frames=len(reference["frames"]),
        fields=fields,
        geometry_exact=True,
        field_values_exact=True,
        history_exact=True,
        source_closed=True,
        retained_owned_records=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-reference", required=True)
    parser.add_argument("--cpp-probe", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    result = compare(
        json.loads(Path(args.python_reference).read_text()),
        json.loads(Path(args.cpp_probe).read_text()),
    )
    Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
