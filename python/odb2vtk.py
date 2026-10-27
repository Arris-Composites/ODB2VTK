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
odb2vtk_core. CLI extraction remains a separate Phase 4 change.
"""

import argparse
import os
import sys
import timeit

from odb2vtk_core.legacy import (
    ODB2VTK,
    ABAQUS_VTK_CELL_MAP,
    ABAQUS_VTK_FIELDOUPUTS_MAP,
)
from odb2vtk_core.converter import MATERIAL_ORIENTATION
from odb2vtk_core.source import AbaqusSource

if __name__ == "__main__":
    start_time = timeit.default_timer()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--header",
        required=True,
        type=int,
        help="if 1, extract header information and generate a .json file. Otherwise, generate .vtu file",
    )
    parser.add_argument(
        "--instance",
        help="selected instance names which are separated by whitespace, e.g. 'instanceName1' 'instanceName2'",
        nargs="*",
    )
    parser.add_argument(
        "--step",
        help="selected step names and frames which are separated by whitespace, e.g., 'step1:1,2,3' 'step2:2,3,4'",
        nargs="*",
    )
    parser.add_argument(
        "--writeHistory", default=0, type=int, help="if 1, write history output."
    )
    parser.add_argument(
        "--odbFile", required=True, help="selected odb file (full path name)"
    )
    parser.add_argument("--writePVD", default=0, type=int, help="if 1 write a pvd file")
    parser.add_argument(
        "--suffix", default="", type=str, help="string appended to the file"
    )
    args = parser.parse_args()

    # check odbfile
    if not args.odbFile:
        sys.exit("Need an .odf file as input")
    if not os.path.exists(args.odbFile):
        sys.exit("{0} doesn't exist".format(args.odbFile))

    with ODB2VTK(args.odbFile, args.suffix) as odb2vtk:
        # if --header is on, ignore all others and extract header information
        if args.header:
            odb2vtk.ExtractHeader()
            sys.exit(
                "{0} generated".format(
                    os.path.join(odb2vtk.odbPath, odb2vtk.odbFileNameNoExt)
                )
            )

        if not args.instance:
            sys.exit("instance not found")

        if not args.step:
            sys.exit("steps and frames not found")

        # args.step - ['step1:1,2,3', 'step2:2,3,4']
        # convert step-frame dictionary to {'stepname': [0, 1, 2, 3], 'stepname': [0,1,2]} format
        step_frame_dict = {}
        for item in args.step:
            split = item.split(":")
            step_frame_dict[split[0]] = []
            for i in split[1].split(","):
                step_frame_dict[split[0]].append(int(i))
        odb2vtk.ReadArgs(args.instance, step_frame_dict)
        if args.writeHistory:
            odb2vtk.WriteCSVFILE()
        if args.writePVD:
            odb2vtk.WritePVDFile()
            sys.exit()

        odb2vtk.WriteVTUFiles()

        print("--- %s seconds ---" % (timeit.default_timer() - start_time))
