"""Create a two-step CLI ordering fixture; run with Abaqus Python."""

from pathlib import Path
import sys

import create_phase2_fixture

if __name__ == "__main__":
    # The existing creator refuses overwrites and closes the new ODB first.
    create_phase2_fixture.main()
    from odbAccess import openOdb
    from abaqusConstants import TIME, NODAL, VECTOR

    path = Path(sys.argv[1]).resolve()
    odb = openOdb(str(path), readOnly=False)
    try:
        step = odb.Step(
            name="Step-2", description="CLI ordering", domain=TIME, timePeriod=2.0
        )
        for index in range(2):
            frame = step.Frame(incrementNumber=index, frameValue=0.5 + index)
            field = frame.FieldOutput(
                name="U", description="Second-step displacement", type=VECTOR
            )
            for instance in odb.rootAssembly.instances.values():
                labels = tuple(node.label for node in instance.nodes)
                field.addData(
                    position=NODAL,
                    instance=instance,
                    labels=labels,
                    data=tuple((label * 0.001 + index, 2.0, 3.0) for label in labels),
                )
        odb.save()
    finally:
        odb.close()
