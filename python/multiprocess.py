# /*=========================================================================
#    Program: ODB2VTK
#    Module:  multiprocess.py
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

# Command line tool to spawn 'abaqus python' call in parallel

import multiprocessing
import subprocess
import argparse
import sys
import os


def spawn(cmd):
    return subprocess.call(cmd, shell=True)


# use multiprocessing to spawn abaqus python call in parallel
if __name__ == "__main__":
    script_dir = os.path.abspath(os.path.dirname(__file__))

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
    parser.add_argument("--writeHistory", type=int, help="if 1, write history output.")
    parser.add_argument(
        "--odbFile", required=True, help="selected odb file (full path name)"
    )
    parser.add_argument(
        "--suffix", default="", type=str, help="string appended to the file"
    )

    args = parser.parse_args()

    if not args.odbFile:
        sys.exit("Need an .odb file as input")
    if not os.path.exists(args.odbFile):
        sys.exit("{0} doesn't exist".format(args.odbFile))
    # if --header is on, ignore all others and extract header information
    if args.header:
        cmd = "abaqus python {0}/odb2vtk.py --header 1 --odbFile {1}".format(
            script_dir, args.odbFile
        )
        spawn(cmd)
        sys.exit()
    if not args.instance:
        sys.exit("Instance not provided.")
    if not args.step:
        sys.exit("Step not provided.")

    # split the frames and run them in parallel
    step_frame_dict = []
    steps = ""
    for item in args.step:
        steps += '"{0}" '.format(item)
        split = item.split(":")
        for i in split[1].split(","):
            step_frame_dict.append("{0}:{1}".format(split[0], int(i)))
    instances = ""
    for inst in args.instance:
        instances += '"{0}"'.format(inst) + " "

    cmd = []
    for step in step_frame_dict:
        if args.suffix == "":
            cmd.append(
                'abaqus python {0}/odb2vtk.py --header 0 --odbFile {1} --instance {2} --step "{3}"'.format(
                    script_dir, args.odbFile, instances, step
                )
            )
        else:
            cmd.append(
                'abaqus python {0}/odb2vtk.py --header 0 --odbFile {1} --instance {2} --step "{3}" --suffix {4}'.format(
                    script_dir, args.odbFile, instances, step, args.suffix
                )
            )
    # append one mroe command to generate PVD file
    if args.suffix == "":
        cmd.append(
            "abaqus python {0}/odb2vtk.py --header 0 --odbFile {1} --instance {2} --step {3} --writePVD 1".format(
                script_dir, args.odbFile, instances, steps
            )
        )
    else:
        cmd.append(
            "abaqus python {0}/odb2vtk.py --header 0 --odbFile {1} --instance {2} --step {3} --writePVD 1 --suffix {4}".format(
                script_dir, args.odbFile, instances, steps, args.suffix
            )
        )
    count = multiprocessing.cpu_count()
    pool = multiprocessing.Pool(processes=count)
    pool.map(spawn, cmd)
