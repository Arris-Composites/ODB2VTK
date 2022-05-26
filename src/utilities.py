# /*=========================================================================
#    Program: ODB2VTK
#    Module:  utilities.py
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
