# /*=========================================================================
#    Program: ODB2VTK
#    Module:  multiprocess.py
#    Copyright (c) Arris Composites Inc.
#    All rights reserved.
#
#    Arris Composites Inc.
#    710 Bancroft Way
#    Berkeley, CA 94710
#    USA
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE AUTHORS OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ========================================================================*/


import multiprocessing
import subprocess
import argparse
import sys
import os

def spawn(cmd):
    return subprocess.call(cmd, shell=True)

# use multiprocessing to spawn abaqus python call in parallel
if __name__ == "__main__":
    script_dir = os.path.abspath( os.path.dirname( __file__ ) )

    parser = argparse.ArgumentParser()
    parser.add_argument("--header", required=True, type=int, \
            help="if 1, extract header information and generate a .json file. Otherwise, generate .vtu file")
    parser.add_argument("--instance", help="selected instance names which are separated by whitespace, e.g. 'instanceName1' 'instanceName2'", nargs="*")
    parser.add_argument("--step", help="selected step names and frames which are separated by whitespace, e.g., 'step1:1,2,3' 'step2:2,3,4'", nargs="*")
    parser.add_argument("--writeHistory", type=int, help="if 1, write history output.")
    parser.add_argument("--odbFile", required=True, help="selected odb file (full path name)")
    args = parser.parse_args()

    if not args.odbFile:
        sys.exit("Need an .odb file as input")
    if not os.path.exists(args.odbFile):
        sys.exit("{0} doesn't exist".format(args.odbFile))
	# if --header is on, ignore all others and extract header information
    if args.header:
        cmd = 'abaqus python {0}/odb2vtk.py --header 1 --odbFile {1}'.format(script_dir, args.odbFile)
        spawn(cmd)
        sys.exit()
    if not args.instance:
        sys.exit("Instance not provided.")
    if not args.step:
        sys.exit("Step not provided.")

    # split the frames and run them in parallel
    step_frame_dict = []
    for item in args.step:
        split = item.split(':')
        for i in split[1].split(','):
            step_frame_dict.append('{0}:{1}'.format(split[0], int(i)))
    instances = ''
    for inst in args.instance:
        instances += '"{0}"'.format(inst) + ' '

    cmd = []
    for step in step_frame_dict:
        cmd.append('abaqus python {0}/odb2vtk.py --header 0 --odbFile {1} --instance {2} --step "{3}"'
                    .format(script_dir, args.odbFile, instances, step))

    count = multiprocessing.cpu_count()
    pool = multiprocessing.Pool(processes=count)
    pool.map(spawn, cmd)