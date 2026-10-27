"""Create a synthetic scaling fixture with Abaqus Python, without a solver.

Usage: abaqus python create_benchmark_odb.py OUTPUT.odb [ELEMENTS] [FRAMES]
Disconnected C3D8R cells, U/RF, four nodal scalars and integration-point stress.
This checks exporter scaling, not realistic solver workloads or every cell family.
"""

from pathlib import Path
import sys


def main():
    from odbAccess import Odb
    from abaqusConstants import (
        THREE_D,
        DEFORMABLE_BODY,
        TIME,
        VECTOR,
        SCALAR,
        TENSOR_3D_FULL,
        NODAL,
        INTEGRATION_POINT,
    )

    path = Path(sys.argv[1]).resolve()
    if path.exists():
        raise FileExistsError(path)
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    frames = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    if count < 1 or frames < 1:
        raise ValueError("Element and frame counts must be positive")
    odb = Odb(name=path.stem, path=str(path))
    try:
        part = odb.Part(name="PART", embeddedSpace=THREE_D, type=DEFORMABLE_BODY)
        corners = (
            (0, 0, 0),
            (1, 0, 0),
            (1, 1, 0),
            (0, 1, 0),
            (0, 0, 1),
            (1, 0, 1),
            (1, 1, 1),
            (0, 1, 1),
        )
        nodes = tuple(
            (8 * i + j + 1, 2 * i + x, y, z)
            for i in range(count)
            for j, (x, y, z) in enumerate(corners)
        )
        part.addNodes(nodeData=nodes)
        part.addElements(
            elementData=tuple(
                (i + 1,) + tuple(range(8 * i + 1, 8 * i + 9)) for i in range(count)
            ),
            type="C3D8R",
        )
        instance = odb.rootAssembly.Instance(name="PART-1-1", object=part)
        step = odb.Step(
            name="Step-1", description="Scaling fixture", domain=TIME, timePeriod=1.0
        )
        labels = tuple(range(1, 8 * count + 1))
        for index in range(frames):
            frame = step.Frame(incrementNumber=index, frameValue=float(index))
            for name in ("U", "RF"):
                field = frame.FieldOutput(name=name, description=name, type=VECTOR)
                field.addData(
                    position=NODAL,
                    instance=instance,
                    labels=labels,
                    data=tuple((label * 0.001 + index, 0.0, 1.0) for label in labels),
                )
            for number in range(4):
                field = frame.FieldOutput(
                    name="TEMP{0}".format(number), description="Scalar", type=SCALAR
                )
                field.addData(
                    position=NODAL,
                    instance=instance,
                    labels=labels,
                    data=tuple((label * 0.001 + number + index,) for label in labels),
                )
            stress = frame.FieldOutput(
                name="S", description="Stress", type=TENSOR_3D_FULL
            )
            stress.addData(
                position=INTEGRATION_POINT,
                instance=instance,
                labels=tuple(range(1, count + 1)),
                data=tuple(
                    (float(label), 2.0, 3.0, 4.0, 5.0, 6.0)
                    for label in range(1, count + 1)
                ),
            )
        odb.save()
    finally:
        odb.close()
    print("Created", path, "elements", count, "nodes", 8 * count, "frames", frames)


if __name__ == "__main__":
    main()
