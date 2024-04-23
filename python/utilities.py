# /*=========================================================================
#    Program: ODB2VTK
#    Module:  utilities.py
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

# utilities.py is another wrapper on top of abaqus python API

import odbAccess


class ReadableOdb(object):
    def __init__(self, odb, readOnly=True):
        self._odb = self.open(odb, readOnly=readOnly)

    def open(self, odb, readOnly):
        return odbAccess.openOdb(odb, readOnly)

    def getFrames(self, stepName):
        return self._odb.steps[stepName].frames

    def getFrame(self, stepName, frameNum):
        return self.getFrames(stepName)[frameNum]

    def getInstance(self, instanceName):
        return self._odb.rootAssembly.instances[instanceName]

    def getNodes(self, instanceName):
        return self.getInstance(instanceName).nodes

    def getElements(self, instanceName):
        return self.getInstance(instanceName).elements

    def getFieldOutputsKeys(self, stepName, frameIdx):
        return self._odb.steps[stepName].frames[frameIdx].fieldOutputs.keys()

    def getFieldOutput(self, stepName, frameIdx, fldName):
        return self._odb.steps[stepName].frames[frameIdx].fieldOutputs[fldName]

    def getFieldOutputs(self, stepName, frameIdx):
        return self._odb.steps[stepName].frames[frameIdx].fieldOutputs.items()

    def getHistoryRegions(self, stepName):
        return self._odb.steps[stepName].historyRegions

    @property
    def odb(self):
        return self._odb

    @property
    def getStepsKeys(self):
        return self._odb.steps.keys()

    @property
    def getInstancesKeys(self):
        return self._odb.rootAssembly.instances.keys()
