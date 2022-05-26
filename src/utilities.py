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
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# ========================================================================*/

# Contributors: Yang Shen and Luis Bahamonde
# utilities.py is another wrapper on top of abaqus python API

import odbAccess

class ReadableOdb(object):
    def __init__(self, odb, readOnly=True):
        self._odb = self.open(odb, readOnly=readOnly)
    
    def open(self, odb, readOnly):
        return odbAccess.openOdb(odb, readOnly)

    def getFrames(self, stepName):
        """Get list of frames, because odb sequences do not allow slicing
        """
        return list(self._odb.steps[stepName].frames)

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
