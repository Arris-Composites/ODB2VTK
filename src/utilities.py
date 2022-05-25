"""Utilities for batch reading odb files

    Requirements
    ------------
    Abaqus/Python

    Use Cases
    ---------
    - report results of FE analysis
"""
from itertools import compress
from collections import Sequence
import odbAccess
from abaqusConstants import CENTROID
from abaqusConstants import QUAD, TRI # shell shapes
from abaqusConstants import HEX, TET # solid shapes
from abaqusConstants import S3R, S3, S4R, S4 # shell codes
from abaqusConstants import C3D4, C3D8R, C3D10 # solid codes
from abaqusConstants import DC3D8 # heat transfer codes
from abaqusConstants import MAX_INPLANE_PRINCIPAL, MIN_INPLANE_PRINCIPAL # plane stress

ELE_CODES = {
    'S3R': S3R,
    'S3': S3,
    'S4R': S4R,
    'S4': S4,
    'C3D8R': C3D8R,
    'C3D4': C3D4,
    'C3D10': C3D10,
    'DC3D8': DC3D8
}

ELE_SHAPES = {
    'S3R': TRI,
    'S3': TRI,
    'S4R': QUAD,
    'S4': QUAD,
    'C3D8R': HEX,
    'C3D4': TET,
    'C3D10': TET,
    'DC3D8': HEX
}

INVARIANT_STRESS = {
    'maxInPlanePrincipal': MAX_INPLANE_PRINCIPAL,
    'minInPlanePrincipal': MIN_INPLANE_PRINCIPAL
}

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
