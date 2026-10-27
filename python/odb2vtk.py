# /*=========================================================================
#    Program: ODB2VTK
#    Module:  odb2vtk.py
#    Copyright (c) Arris Composites Inc.
#    All rights reserved.
#
#    Arris Composites Inc.
#    745 Heinz Ave
#    Berkeley, CA 94710
#    USA
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ========================================================================*/

"""Existing command-line entry point and legacy library imports.

New library users can import Converter, Selection, and OutputOptions from
odb2vtk_core. The executable delegates to odb2vtk_core.cli.main.
"""

import sys
from importlib import import_module

from odb2vtk_core.cli import main

_EXPORTS = {
    "ODB2VTK": "odb2vtk_core.legacy",
    "ABAQUS_VTK_CELL_MAP": "odb2vtk_core.legacy",
    "ABAQUS_VTK_FIELDOUPUTS_MAP": "odb2vtk_core.legacy",
    "MATERIAL_ORIENTATION": "odb2vtk_core.converter",
    "AbaqusSource": "odb2vtk_core.source",
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(_EXPORTS[name]), name)
    globals()[name] = value
    return value


if __name__ == "__main__":
    sys.exit(main())
