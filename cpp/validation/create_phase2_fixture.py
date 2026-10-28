"""Create small mixed-element/section fixtures using Abaqus Python, no solver."""

import argparse
from pathlib import Path


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

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--no-stress", action="store_true")
    args = parser.parse_args()
    path = Path(args.output).resolve()
    if path.exists():
        raise FileExistsError(path)
    odb = Odb(name=path.stem, path=str(path))
    try:
        category = odb.SectionCategory(name="Layers", description="Validation layers")
        sections = [
            category.SectionPoint(number=i, description=name)
            for i, name in ((1, "Top"), (2, "Bottom"))
        ]
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
        part.addNodes(
            nodeData=tuple(
                ((8 * i + j + 1) * 10, 2 * i + x, y, z)
                for i in range(4)
                for j, (x, y, z) in enumerate(corners)
            )
        )
        for kind, indices in (("C3D8", (0, 1)), ("C3D8R", (2, 3))):
            part.addElements(
                elementData=tuple(
                    ((i + 1) * 10,)
                    + tuple(node * 10 for node in range(8 * i + 1, 8 * i + 9))
                    for i in indices
                ),
                type=kind,
                sectionCategory=category,
            )
        instances = [
            odb.rootAssembly.Instance(name=name, object=part) for name in ("A", "B")
        ]
        step = odb.Step(
            name="Step-1", description="Mixed IP counts", domain=TIME, timePeriod=1.0
        )
        labels = tuple(range(10, 321, 10))
        for index in range(2):
            frame = step.Frame(incrementNumber=index, frameValue=float(index))
            displacement = frame.FieldOutput(
                name="U", description="Displacement", type=VECTOR
            )
            scalar = frame.FieldOutput(name="TEMP", description="Scalar", type=SCALAR)
            stress = (
                None
                if args.no_stress
                else frame.FieldOutput(
                    name="S", description="Stress", type=TENSOR_3D_FULL
                )
            )
            for instance_index, instance in enumerate(instances):
                offset = instance_index * 100 + index * 10
                displacement.addData(
                    position=NODAL,
                    instance=instance,
                    labels=labels,
                    data=tuple(
                        (label * 0.001 + offset, label * 0.002, -label * 0.003)
                        for label in labels
                    ),
                )
                scalar.addData(
                    position=NODAL,
                    instance=instance,
                    labels=labels,
                    data=tuple((label * 0.01 + offset,) for label in labels),
                )
                if stress is not None:
                    for section_index, section in enumerate(sections):
                        for elements, points in (((10, 20), 8), ((30, 40), 1)):
                            stress.addData(
                                position=INTEGRATION_POINT,
                                instance=instance,
                                labels=elements,
                                sectionPoint=section,
                                data=tuple(
                                    tuple(
                                        float(
                                            element
                                            + point * 0.01
                                            + component * 0.001
                                            + offset
                                            + section_index * 1000
                                        )
                                        for component in range(6)
                                    )
                                    for element in elements
                                    for point in range(1, points + 1)
                                ),
                            )
        odb.save()
    finally:
        odb.close()
    print("Created", path)


if __name__ == "__main__":
    main()
