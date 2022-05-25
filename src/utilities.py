"""Utilities for batch reading odb files

    Requirements
    ------------
    Abaqus/Python

    Use Cases
    ---------
    - report results of FE analysis
"""
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
