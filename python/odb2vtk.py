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

# ODB2VTK class to access the data inside odb file and write it into vtu

import utilities

# import necessary modules to handle Abaqus output database, files and string
import numpy as np
from odbAccess import *
from string import *
from time import *
import os
import sys
import json
import argparse
import timeit


# abaqus position
from abaqusConstants import NODAL, INTEGRATION_POINT, ELEMENT_NODAL, CENTROID

# abaqus datatype
# see https://abaqus-docs.mit.edu/2017/English/SIMACAECMDRefMap/simacmd-c-odbintrowritefieldpyc.htm
from abaqusConstants import (
    SCALAR,
    VECTOR,
    TENSOR_3D_FULL,
    TENSOR_3D_SURFACE,
    TENSOR_3D_PLANAR,
    TENSOR_2D_SURFACE,
    TENSOR_2D_PLANAR,
)

MATERIAL_ORIENTATION = "Material_Orientation"


def ABAQUS_VTK_CELL_MAP(abaqusElementType):
    # this function maps the abaqus element type to vtk cell type
    # linear cell
    # https://raw.githubusercontent.com/Kitware/vtk-examples/gh-pages/src/Testing/Baseline/Cxx/GeometricObjects/TestLinearCellDemo.png
    # quadratic cell
    # https://raw.githubusercontent.com/Kitware/vtk-examples/gh-pages/src/Testing/Baseline/Cxx/GeometricObjects/TestIsoparametricCellsDemo.png

    if "C3D4" in abaqusElementType:
        return 10
    elif "C3D6" in abaqusElementType:
        return 13
    elif "C3D8" in abaqusElementType:
        return 12
    elif "C3D10" in abaqusElementType:
        return 24
    elif "C3D15" in abaqusElementType:
        return 26
    elif "C3D20" in abaqusElementType:
        return 25
    elif "S3" in abaqusElementType:
        return 5
    elif "S4" in abaqusElementType:
        return 9
    elif "S8" in abaqusElementType:
        return 23
    elif "S9" in abaqusElementType:
        return 28
    elif "B31" in abaqusElementType:
        return 3
    elif "R3D3" in abaqusElementType:
        return 5
    elif "R3D4" in abaqusElementType:
        return 9
    else:
        sys.exit("{0} element type not found".format(abaqusElementType))
        return None


def ABAQUS_VTK_FIELDOUPUTS_MAP(fldOutput):
    # output convention: (vtkType, abaqusComponentLabels, abaqusPosition)

    # TODO: assuming fldOutput.locations always have a size of 1.
    # in the future maybe extend this to handle more than one location
    abaqusDataType = fldOutput.type
    abaqusComponentLabels = fldOutput.componentLabels
    abaqusPosition = fldOutput.locations[0].position

    vtkType = None
    # position = None

    if abaqusDataType == SCALAR:
        vtkType = "Scalars"
        # scalar values have zero componentLabels
        # assign a default one here
        if len(abaqusComponentLabels) == 0:
            abaqusComponentLabels = "0"
    elif abaqusDataType == VECTOR:
        vtkType = "Vectors"
    elif abaqusDataType == TENSOR_3D_FULL:
        vtkType = "Tensors"
    elif abaqusDataType == TENSOR_3D_SURFACE:
        vtkType = "Tensors"
    elif abaqusDataType == TENSOR_3D_PLANAR:
        vtkType = "Tensors"
    elif abaqusDataType == TENSOR_2D_SURFACE:
        vtkType = "Tensors"
    elif abaqusDataType == TENSOR_2D_PLANAR:
        vtkType = "Tensors"
    else:
        vtkType = "Tensors"

    return (vtkType, abaqusComponentLabels, abaqusPosition)


###########################################################
class ODB2VTK:
    def __init__(self, fileFullName, suffix):
        self.fileFullName = fileFullName
        self.odbFileName = os.path.basename(fileFullName)
        self.odbFileNameNoExt = self.odbFileName.split(".")[0] + suffix
        self.odbPath = os.path.dirname(fileFullName)

        self.odb = utilities.ReadableOdb(self.fileFullName)
        # private variables
        # nodes and elements map are nested dictionary
        # {'instanceName': {'nodeLabel1': 0, 'nodeLabel1': 0, ...}, .....}
        self._nodes_map = {}
        self._elements_map = {}
        self._instance_names = []
        self._step_frame_map = {}
        self._nodesNum = 0
        self._cellsNum = 0

    def ExtractHeader(self):
        dictJson = {"instances": [], "steps": []}

        print("Scan instances...")
        for instanceName in self.odb.getInstancesKeys:
            dictJson["instances"].append(instanceName)

        print("Scan steps and frames...")
        for stepName in self.odb.getStepsKeys:
            step_frame_map = []
            step_frame_map.append(stepName)
            frames = []
            frameNum = len(self.odb.getFrames(stepName))
            for i in range(frameNum):
                frames.append(
                    stepName + "-frame-{0}".format(str(i).zfill(len(str(frameNum))))
                )
                print(stepName + "-frame-{0}".format(str(i).zfill(len(str(frameNum)))))
            step_frame_map.append(frames)
            dictJson["steps"].append(step_frame_map)

        with open(
            os.path.join(self.odbPath, self.odbFileNameNoExt) + ".json", "w"
        ) as fp:
            json.dump(dictJson, fp, 4)

    # instanceNames = ['names', 'names']
    # stepFrameDict = {'stepname': [0, 1, 2, 3], 'stepname': [0,1,2]}
    def ReadArgs(self, instanceNames, stepsFramesDict):
        self._instance_names = instanceNames
        self._step_frame_map = stepsFramesDict

    def ConstructMap(self):
        # self._nodes_map = {{node.label: index}, {}}
        self._nodes_map.clear()
        self._elements_map.clear()
        self._nodesNum = 0
        self._cellsNum = 0
        indexNode = 0
        indexElement = 0
        for i, instanceName in enumerate(self._instance_names):
            self._nodes_map[instanceName] = {}
            self._elements_map[instanceName] = {}
            nodes = self.odb.getNodes(instanceName)
            elements = self.odb.getElements(instanceName)
            self._nodesNum += len(nodes)
            self._cellsNum += len(elements)
            for i in range(len(nodes)):
                self._nodes_map[instanceName][nodes[i].label] = indexNode
                indexNode += 1
            for i in range(len(elements)):
                self._elements_map[instanceName][elements[i].label] = indexElement
                indexElement += 1

    def WriteFieldOutputData(
        self, fldName, stepName, frameIdx, pointdata_map, celldata_map
    ):
        fldOutput = self.odb.getFieldOutput(stepName, frameIdx, fldName)
        vtkData = ABAQUS_VTK_FIELDOUPUTS_MAP(fldOutput)
        bufferPointDataArray = ""
        bufferCellDataArray = ""
        # if fieldOutput contains sectionPoint data, we need to generate separate dataset
        sectionPointMap = {}
        maxNumOfIntegrationPoint = 1
        for instanceName in self._instance_names:
            # get data block of the instance
            subset = fldOutput.getSubset(region=self.odb.getInstance(instanceName))
            # filter by position
            # note that subset.bulkDataBlocks may have more than one
            # because of different element type or sectionPoint in the same instance
            subset = subset.getSubset(position=vtkData[2])
            # we are checking the bulkDataBlocks here
            # We need to write vtu data according to what is included in bulkDataBlocks
            # we are assuming that element in one instance should be consistent in terms of sectionPoint
            # i.e., they either all have sectionPoint, or don't have sectionPoint
            for block in subset.bulkDataBlocks:
                if block.sectionPoint is not None:
                    sectionPointMap[block.sectionPoint.description] = block.sectionPoint
                if block.integrationPoints is not None:
                    if maxNumOfIntegrationPoint < block.integrationPoints.max():
                        maxNumOfIntegrationPoint = block.integrationPoints.max()

        if vtkData[2] == NODAL:
            bufferPointDataArray += self.WriteDataArrayWithSectionPoints(
                sectionPointMap, fldOutput, vtkData, fldName, pointdata_map, "PointData"
            )
        if vtkData[2] == INTEGRATION_POINT:
            # visualize the data based on the value at the centroid from Abaqus
            vtkDataNew = (vtkData[0], vtkData[1], CENTROID)
            bufferCellDataArray += self.WriteDataArrayWithSectionPoints(
                sectionPointMap,
                fldOutput,
                vtkDataNew,
                fldName + "_Centroid",
                celldata_map,
                "CellData",
            )
            # we also want to store the values for each integration point
            vtkDataNew = (vtkData[0], vtkData[1] * maxNumOfIntegrationPoint, vtkData[2])
            bufferCellDataArray += self.WriteDataArrayWithSectionPoints(
                sectionPointMap,
                fldOutput,
                vtkDataNew,
                fldName + "_IntegrationPoints",
                celldata_map,
                "CellData",
            )
        # if vtkData[2] == CENTROID:
        # 	bufferCellDataArray += self.WriteDataArrayWithSectionPoints(sectionPointMap, fldOutput, vtkData, fldName, celldata_map, "CellData")
        return (bufferPointDataArray, bufferCellDataArray)

    def WriteDataArrayWithSectionPoints(
        self, sectionPointMap, fldOutput, vtkData, fldName, data_map, dataType
    ):
        buffer = ""
        if len(sectionPointMap) == 0:
            # meaning we don't have any sectionPoint in the current fieldOutput
            # generate one dataset
            buffer += self.WriteDataArray(fldOutput, vtkData, fldName, dataType)
            data_map[vtkData[0]].append(fldName)
        else:
            # meaning we have sectionPoint in the current fieldOutput
            # we need to split the data
            for description, sectionP in sectionPointMap.items():
                subset = fldOutput.getSubset(sectionPoint=sectionP)
                buffer += self.WriteDataArray(
                    subset, vtkData, fldName + description, dataType
                )
                data_map[vtkData[0]].append(fldName + description)
        return buffer

    def WriteDataArray(self, fldOutput, vtkData, description, dataType):
        buffer = '<DataArray type="Float32" Name="{0}" NumberOfComponents="{1}"'.format(
            description, len(vtkData[1])
        )
        # use the same component label from Abaqus
        for i, label in enumerate(vtkData[1]):
            buffer += ' ComponentName{0}="{1}"'.format(i, label)
        buffer += ' format="ascii">' + "\n"

        writer = None
        size = 0
        if dataType == "PointData":
            writer = self.WriteSortedPointData
            size = self._nodesNum
        elif dataType == "CellData":
            writer = self.WriteSortedCellData
            size = self._cellsNum
        dataArray = np.zeros((size, len(vtkData[1])))
        for instanceName in self._instance_names:
            subset = fldOutput.getSubset(region=self.odb.getInstance(instanceName))
            subset = subset.getSubset(position=vtkData[2])
            writer(subset.bulkDataBlocks, instanceName, dataArray)
        # can we make this faster???
        for data in dataArray:
            for d in data:
                buffer += "{0} ".format(d)
            buffer += "\n"
        buffer += "</DataArray>" + "\n"
        return buffer

    def WriteSortedPointData(self, bulkDataBlocks, instanceName, pointDataArray):
        if bulkDataBlocks is None:
            return
        for block in bulkDataBlocks:
            indices = [
                self._nodes_map[instanceName][label] for label in block.nodeLabels
            ]
            pointDataArray[indices] = block.data

    def WriteSortedCellData(self, bulkDataBlocks, instanceName, cellDataArray):
        if bulkDataBlocks is None:
            return
        for block in bulkDataBlocks:
            if block.integrationPoints is not None:
                # note that different block may have different number of integration points.
                # unfilled entries are assumed to be zero
                indices = [
                    self._elements_map[instanceName][label]
                    for label in np.unique(block.elementLabels)
                ]
                row, column = map(int, block.data.shape)
                n = block.integrationPoints.max()
                cellDataArray[indices, 0 : column * n] = block.data.reshape(
                    row / n, column * n
                )
            else:
                indices = [
                    self._elements_map[instanceName][label]
                    for label in block.elementLabels
                ]
                cellDataArray[indices] = block.data

    def WriteLocalCS(self, fldName, stepName, frameIdx, celldata_map):
        # this function is to extract material orientation and write it as a vector data at cell.
        buffer = (
            '<DataArray type="Float32" Name="{0}" NumberOfComponents="3" format="ascii">'.format(
                fldName
            )
            + "\n"
        )
        fldOutput = self.odb.getFieldOutput(stepName, frameIdx, "S")
        tempSectionPoint = None
        for instanceName in self._instance_names:
            subset = fldOutput.getSubset(region=self.odb.getInstance(instanceName))
            subset = subset.getSubset(position=CENTROID)
            for block in subset.bulkDataBlocks:
                tempSectionPoint = block.sectionPoint
                break
            break

        cellDataArray = np.zeros((self._cellsNum, 4))
        for instanceName in self._instance_names:
            subset = fldOutput.getSubset(region=self.odb.getInstance(instanceName))
            subset = subset.getSubset(position=CENTROID)
            if tempSectionPoint is not None:
                subset = subset.getSubset(sectionPoint=tempSectionPoint)

            for block in subset.bulkDataBlocks:
                if block.localCoordSystem is not None:
                    indices = [
                        self._elements_map[instanceName][label]
                        for label in block.elementLabels
                    ]
                    cellDataArray[indices, : len(block.localCoordSystem[0])] = (
                        block.localCoordSystem
                    )

        for data in cellDataArray:
            # note that localCoordSystem return here is quaternion
            # see http://130.149.89.49:2080/v6.14/books/ker/default.htm?startat=pt02ch61pyo05.html
            q1 = data[0]
            q2 = data[1]
            q3 = data[2]
            q4 = data[3]  # scalar term
            # convert quaternion to directional cosine
            # x y z is the orientation of 11
            # https://www.vectornav.com/resources/inertial-navigation-primer/math-fundamentals/math-attitudetran
            x = q4**2 + q1**2 - q2**2 - q3**2
            y = 2 * (q1 * q2 - q3 * q4)
            z = 2 * (q1 * q3 + q2 * q4)
            buffer += "{0} {1} {2}".format(x, y, z)
            buffer += "\n"

        buffer += "</DataArray>" + "\n"
        celldata_map["Vectors"].append(fldName)
        return buffer

    def WriteVTUFiles(self):
        for stepName, frameList in self._step_frame_map.items():
            for frameIdx in frameList:
                self.WriteVTUFile([stepName, frameIdx])

    def WriteVTUFile(self, args):
        stepName = args[0]
        frameIdx = args[1]

        # start writing the buffer
        buffer = (
            '<VTKFile type="UnstructuredGrid" version="1,0" byte_order="LittleEndian">'
            + "\n"
        )
        cellConnectivityBuffer = ""
        cellOffsetBuffer = ""
        cellTypeBuffer = ""
        offset = 0
        buffer += "<UnstructuredGrid>" + "\n"
        buffer += (
            '<Piece NumberOfPoints="{0}" NumberOfCells="{1}">'.format(
                self._nodesNum, self._cellsNum
            )
            + "\n"
        )
        buffer += "<Points>" + "\n"
        buffer += (
            '<DataArray type="Float64" NumberOfComponents="3" format="ascii">' + "\n"
        )
        for instanceName in self._instance_names:
            # write nodes
            for node in self.odb.getNodes(instanceName):
                coord = node.coordinates
                buffer += "{0} {1} {2}".format(coord[0], coord[1], coord[2]) + "\n"
            # let's write cell connectivity, offset, and type into a different buffer which will be used later
            for cell in self.odb.getElements(instanceName):
                ## connectivity
                for nodeLabel in cell.connectivity:
                    cellConnectivityBuffer += "{0} ".format(
                        self._nodes_map[instanceName][nodeLabel]
                    )
                cellConnectivityBuffer += "\n"
                ## offset
                offset += len(cell.connectivity)
                cellOffsetBuffer += "{0} ".format(offset) + "\n"
                ## type
                cellTypeBuffer += "{0} ".format(ABAQUS_VTK_CELL_MAP(cell.type)) + "\n"
        buffer += "</DataArray>" + "\n"
        buffer += "</Points>" + "\n"

        # write field data
        print("    writing field data")
        pointdata_map = {"Tensors": [], "Vectors": [], "Scalars": []}
        celldata_map = {"Tensors": [], "Vectors": [], "Scalars": []}
        bufferPointDataArray = ""
        bufferCellDataArray = ""
        for fldName, _ in self.odb.getFieldOutputs(stepName, frameIdx):
            pBuffer, cBuffer = self.WriteFieldOutputData(
                fldName, stepName, frameIdx, pointdata_map, celldata_map
            )
            bufferPointDataArray += pBuffer
            bufferCellDataArray += cBuffer

        # add material local coordinate CS
        bufferCellDataArray += self.WriteLocalCS(
            MATERIAL_ORIENTATION, stepName, frameIdx, celldata_map
        )

        # pointdata - e.g., U, RF
        # <PointData>
        print("    writing PointData")
        buffer += "<PointData "
        for dataArrayField, fldNames in pointdata_map.items():
            if len(fldNames) != 0:
                buffer += dataArrayField + "="
                buffer += "\"'{0}'".format(fldNames[0])
                for i in range(1, len(fldNames)):
                    buffer += ",'{0}'".format(fldNames[i])
                buffer += '" '
        buffer += ">" + "\n"
        # <DataArray>
        buffer += bufferPointDataArray
        buffer += "</PointData>" + "\n"

        # celldata - e.g., S, E
        # <CellData>
        print("    writing CellData")
        buffer += "<CellData "
        for dataArrayField, fldNames in celldata_map.items():
            if len(fldNames) != 0:
                buffer += dataArrayField + "="
                buffer += "\"'{0}'".format(fldNames[0])
                for i in range(1, len(fldNames)):
                    buffer += ",'{0}'".format(fldNames[i])
                buffer += '" '
        buffer += ">" + "\n"
        # <DataArray>
        buffer += bufferCellDataArray
        buffer += "</CellData>" + "\n"

        # write cells
        print("    writing cell connectivity, offsets, and types")
        buffer += "<Cells>" + "\n"
        buffer += '<DataArray type="Int64" Name="connectivity" format="ascii">' + "\n"
        buffer += cellConnectivityBuffer
        buffer += "</DataArray>" + "\n"

        buffer += '<DataArray type="Int64" Name="offsets" format="ascii">' + "\n"
        buffer += cellOffsetBuffer
        buffer += "</DataArray>" + "\n"

        buffer += '<DataArray type="Int64" Name="types" format="ascii">' + "\n"
        buffer += cellTypeBuffer
        buffer += "</DataArray>" + "\n"
        buffer += "</Cells>" + "\n"

        buffer += "</Piece>" + "\n"
        buffer += "</UnstructuredGrid>" + "\n"
        buffer += "</VTKFile>"
        print("Complete.")

        with open(
            "{0}".format(
                self.GetExportFileName(stepName + "_" + str(frameIdx)) + ".vtu"
            ),
            "w",
        ) as f:
            f.write(buffer)
            print("writing " + f.name)

    def WritePVDFile(self):
        buffer = (
            '<VTKFile type="Collection" version="1.0" byte_order="LittleEndian" header_type="UInt64">'
            + "\n"
        )
        buffer += "<Collection>" + "\n"
        partId = 0
        for stepName, frameList in self._step_frame_map.items():
            for frameIdx in frameList:
                fileName = stepName + "_" + str(frameIdx) + ".vtu"
                buffer += (
                    '<DataSet timestep="{0}" part="{1}" file="{2}"/>'.format(
                        self.odb.getFrame(stepName, frameIdx).frameValue,
                        partId,
                        fileName,
                    )
                    + "\n"
                )
                partId += 1
        buffer += "</Collection>" + "\n"
        buffer += "</VTKFile>"

        with open(
            "{0}".format(self.GetExportFileName(self.odbFileNameNoExt) + ".pvd"), "w"
        ) as f:
            f.write(buffer)
            print("{0} file completed.".format(f.name))

    def WriteCSVFILE(self):
        # extract all the historyOutputs from Abaqus and save them into CSV file
        # TODO: we are assuming all historyOutput types are SCALAR.
        # Need to include other types in the future.
        numOfDataArray = 0
        numOfDataPoint = 0
        for stepName in self._step_frame_map.keys():
            for historyRegionName, historyRegionObj in self.odb.getHistoryRegions(
                stepName
            ).items():
                for (
                    historyOutputName,
                    historyOutputObj,
                ) in historyRegionObj.historyOutputs.items():
                    numOfDataArray += 1
                    if numOfDataPoint < len(historyOutputObj.data):
                        numOfDataPoint = len(historyOutputObj.data)

        data = np.zeros((numOfDataPoint, numOfDataArray))
        header = []
        for stepName in self._step_frame_map.keys():
            for historyRegionName, historyRegionObj in self.odb.getHistoryRegions(
                stepName
            ).items():
                for j, (historyOutputName, historyOutputObj) in enumerate(
                    historyRegionObj.historyOutputs.items()
                ):
                    name = stepName + "_" + historyRegionName + "_" + historyOutputName
                    header.append(name)
                    for i, d in enumerate(historyOutputObj.data):
                        data[i][j] = d[1]

        with open(
            "{0}".format(self.GetExportFileName(self.odbFileNameNoExt) + ".csv"), "w"
        ) as f:
            np.savetxt(f, np.array([header]), "%s", ",")
            np.savetxt(f, data, "%f", ",")

    def GetExportFileName(self, filName):
        if not os.path.exists(os.path.join(self.odbPath, self.odbFileNameNoExt)):
            os.mkdir(os.path.join(self.odbPath, self.odbFileNameNoExt))
        return os.path.join(self.odbPath, self.odbFileNameNoExt, filName)


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

    odb2vtk = ODB2VTK(args.odbFile, args.suffix)
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

    odb2vtk.ConstructMap()
    odb2vtk.WriteVTUFiles()

    print("--- %s seconds ---" % (timeit.default_timer() - start_time))
