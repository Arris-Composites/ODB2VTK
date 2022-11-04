#include "odb2vtk.h"
#include "odb_Enum.h"

#include <iostream>
#include <fstream>
#include <sstream>

namespace GLOBAL {
	/// <summary>
	/// A static function to map from abaqus element to vtk cell
	/// Use the same pattern to add a new element
	/// </summary>
	/// <param name="abqElementType"></param>
	/// <returns></returns>
	int ABAQUS_VTK_CELL_MAP(const char* abqElementType)
	{
		std::string type(abqElementType);
		if (type.find("C3D4") != std::string::npos)
		{
			return 10;
		}
		else if (type.find("C3D6") != std::string::npos)
		{
			return 13;
		}
		else if (type.find("C3D8") != std::string::npos)
		{
			return 12;
		}
		else if (type.find("C3D10") != std::string::npos)
		{
			return 24;
		}
		else if (type.find("C3D15") != std::string::npos)
		{
			return 26;
		}
		else if (type.find("C3D20") != std::string::npos)
		{
			return 25;
		}
		else if (type.find("S3") != std::string::npos)
		{
			return 5;
		}
		else if (type.find("S4") != std::string::npos)
		{
			return 9;
		}
		else if (type.find("S8") != std::string::npos)
		{
			return 23;
		}
		else if (type.find("S9") != std::string::npos)
		{
			return 28;
		}
		else if (type.find("B31") != std::string::npos)
		{
			return 3;
		}
		else if (type.find("R3D3") != std::string::npos)
		{
			return 5;
		}
		else if (type.find("R3D4") != std::string::npos)
		{
			return 9;
		}

		std::cerr << type << " not supported by the converter." << std::endl;
		return -1;
	}

	enum OutputDataType {
		PointData,
		CellData,
	};

	std::string ABAQUS_VTK_FIELDOUTPUTS_MAP(const odb_FieldOutput& fldOutput)
	{
		// map abaqus data type to vtk type Scalars, Vectors, Tensors
		if (fldOutput.type() == odb_Enum::odb_DataTypeEnum::SCALAR)
		{
			return "Scalars";
		}
		else if (fldOutput.type() == odb_Enum::odb_DataTypeEnum::VECTOR)
		{
			return "Vectors";
		}
		else if (fldOutput.type() == odb_Enum::odb_DataTypeEnum::TENSOR_3D_FULL ||
			fldOutput.type() == odb_Enum::odb_DataTypeEnum::TENSOR_3D_SURFACE ||
			fldOutput.type() == odb_Enum::odb_DataTypeEnum::TENSOR_3D_PLANAR ||
			fldOutput.type() == odb_Enum::odb_DataTypeEnum::TENSOR_2D_SURFACE ||
			fldOutput.type() == odb_Enum::odb_DataTypeEnum::TENSOR_2D_PLANAR)
		{
			return "Tensors";
		}
		
		std::cerr << "VTK field data type not understood." << std::endl;
		return "";
	}
}


odb2vtk::odb2vtk(const char* odbFullname, const char* suffix)
{
	odb_String odbFile = odb_String(odbFullname);
	m_odbFullName = std::string(odbFullname);
	m_odbPath = m_odbFullName.substr(0, m_odbFullName.find_last_of("/\\"));
	m_odbBaseName = m_odbFullName.substr(m_odbFullName.find_last_of("/\\") + 1);
	m_odb = &openOdb(odbFile);
}

odb2vtk::~odb2vtk()
{
	m_odb->close();
}

void odb2vtk::ExtractHeader()
{
	if (m_odb != nullptr) 
	{
		auto filename = m_odbPath + "/header.txt";
		std::ofstream header(filename);
		if (header.is_open()) 
		{
			// write instances 
			odb_InstanceRepositoryIT instIter(m_odb->rootAssembly().instances());
			header << "instances: ";
			for (instIter.first(); !instIter.isDone(); instIter.next())
			{
				header << instIter.currentKey().CStr() << " ";
			}
			header << "\n";
			// write steps and frames
			odb_StepRepositoryIT stepIter(m_odb->steps());
			for (stepIter.first(); !stepIter.isDone(); stepIter.next())
			{
				header << stepIter.currentKey().CStr() << ": ";
				for (int i = 0; i < stepIter.currentValue().frames().size(); i++)
				{
					header << i << " ";
				}
				header << "\n";
			}
		}
	}
}

void odb2vtk::ReadArgs(const std::vector<std::string>& instanceNames,
	const std::map<std::string, std::vector<int>>& stepFrameMap)
{
	m_instanceNames = instanceNames;
	m_stepFrameMap = stepFrameMap;
}

void odb2vtk::WriteCSVFile()
{
}

void odb2vtk::WritePVDFile()
{
}

void odb2vtk::ConstructMap()
{
	m_nodesMap.clear();
	m_cellsMap.clear();
	m_nodesNum = 0;
	m_cellsNum = 0;
	// global index used in paraview for node and cell.
	int nodeIndex = 0; 
	int cellIndex = 0;

	// we need to map the local label from abaqus to global index for paraview.
	for (const auto& inst_name : m_instanceNames)
	{
		m_nodesMap[inst_name] = std::map<int, int>();
		m_cellsMap[inst_name] = std::map<int, int>();
		auto rootAssy = m_odb->rootAssembly();
		auto inst = rootAssy.instances()[inst_name.c_str()];
		auto node_list = inst.nodes();
		auto cell_list = inst.elements();
		m_nodesNum += node_list.size();
		m_cellsNum += cell_list.size();
		for (int i = 0; i < node_list.size(); i++)
		{
			auto node = node_list[i];
			m_nodesMap[inst_name][node.label()] = nodeIndex;
			nodeIndex++;
		}
		for (int i = 0; i < cell_list.size(); i++)
		{
			auto cell = cell_list[i];
			m_cellsMap[inst_name][cell.label()] = cellIndex;
			cellIndex++;
		}
	}

}

void odb2vtk::WriteFieldOutputData(
	const char* stepName, 
	int frameIdx, 
	std::map<std::string, std::vector<std::string>>& o_PointdataMap, 
	std::map<std::string, std::vector<std::string>>& o_CelldataMap,
	std::string& o_bufferPointdataArray,
	std::string& o_bufferCelldataArray)
{
	auto fldOutputs = m_odb->steps().constGet(stepName).frames()[frameIdx].fieldOutputs();
	odb_FieldOutputRepositoryIT fieldIter(fldOutputs);
	for (fieldIter.first(); !fieldIter.isDone(); fieldIter.next())
	{
		auto fldOutput = fieldIter.currentValue();
		std::string vtk_type = GLOBAL::ABAQUS_VTK_FIELDOUTPUTS_MAP(fldOutput);

		// assuming location only has size of 1
		// TODO: may need to consider cases with locations more than 1
		auto abqPos = fldOutput.locations().constGet(0).position();
		// if fieldoutput contains sectionPoint data, we need to generate separate dataset

		// purpose of this loop is to iterate over fieldouput from all the instance 
		// and check to see if we can find any section points
		std::vector<odb_SectionPoint> sectionPoints;
		int maxNumIntegrationPoints = 1;
		for (const auto& inst_name : m_instanceNames)
		{
			auto inst = m_odb->rootAssembly().instances().constGet(inst_name.c_str());
			//get data block of the instance
			//filter by position
			//note that subset.bulkDataBlocks may have more than one
			//because of different element type or sectionPoint in the same instance
			auto subset = fldOutput.getSubset(inst).getSubset(abqPos);
			for (int i = 0; i < subset.bulkDataBlocks().size(); i++)
			{
				auto blk = subset.bulkDataBlocks()[i];
				auto sectionPoint = blk.sectionPoint();
				if (sectionPoint.number() != -1)
				{
					sectionPoints.push_back(sectionPoint);
				}
				// number of integration points is calculated by dividing bulkdata length by number of elements within the bulk
				// the purpose of this is that we need to track the maximum number of integration point among all instances
				// and use max to fill in the VTK data entry
				if (blk.numberOfElements() != 0)
				{
					int num_ip = blk.length() / blk.numberOfElements();
					if (num_ip > maxNumIntegrationPoints)
					{
						maxNumIntegrationPoints = num_ip;
					}
				}
			}
		}

		if (abqPos == odb_Enum::odb_ResultPositionEnum::NODAL)
		{
			this->WriteDataArrayWithSectionPoints(sectionPoints,
				fldOutput, 
				abqPos, 
				fldOutput.name(),
				maxNumIntegrationPoints,
				GLOBAL::OutputDataType::PointData,
				o_PointdataMap,
				o_bufferPointdataArray);
		}
		else if (abqPos == odb_Enum::odb_ResultPositionEnum::INTEGRATION_POINT)
		{
			// first write the data at the centroid of the cell
			this->WriteDataArrayWithSectionPoints(sectionPoints,
				fldOutput,
				odb_Enum::odb_ResultPositionEnum::CENTROID,
				fldOutput.name() + "_Centroid",
				1,
				GLOBAL::OutputDataType::CellData,
				o_CelldataMap,
				o_bufferCelldataArray);
			// then write the data for all integration points
			// so one cell will get a total number of maxNumIntegrationPoints * numOfComponents components
			this->WriteDataArrayWithSectionPoints(sectionPoints,
				fldOutput,
				abqPos,
				fldOutput.name() + "_IntegrationPoints",
				maxNumIntegrationPoints,
				GLOBAL::OutputDataType::CellData,
				o_CelldataMap,
				o_bufferCelldataArray);
		}
	}
}

void odb2vtk::WriteDataArrayWithSectionPoints(
	const std::vector<odb_SectionPoint>& sectionPoints,
	const odb_FieldOutput& fldOutput,
	const odb_Enum::odb_ResultPositionEnum& pos,
	const odb_String& fldName,
	int maxNumOfIntegrationPoints,
	const GLOBAL::OutputDataType& outputDatatype,
	std::map<std::string, std::vector<std::string>>& o_dataMap,
	std::string& o_buffer)
{
	if (sectionPoints.empty())
	{
		this->WriteDataArray(fldOutput, fldName, outputDatatype, pos, maxNumOfIntegrationPoints, o_buffer);
		if (o_dataMap.find(GLOBAL::ABAQUS_VTK_FIELDOUTPUTS_MAP(fldOutput)) == o_dataMap.end())
		{
			o_dataMap[GLOBAL::ABAQUS_VTK_FIELDOUTPUTS_MAP(fldOutput)] = std::vector<std::string>();
		}
		o_dataMap[GLOBAL::ABAQUS_VTK_FIELDOUTPUTS_MAP(fldOutput)].push_back(fldName.cStr());
	}
	for (const auto& sp : sectionPoints)
	{
		auto subset = fldOutput.getSubset(sp);
		this->WriteDataArray(subset, fldName + sp.description(), outputDatatype, pos, maxNumOfIntegrationPoints, o_buffer);
		if (o_dataMap.find(GLOBAL::ABAQUS_VTK_FIELDOUTPUTS_MAP(fldOutput)) == o_dataMap.end())
		{
			o_dataMap[GLOBAL::ABAQUS_VTK_FIELDOUTPUTS_MAP(fldOutput)] = std::vector<std::string>();
		}
		o_dataMap[GLOBAL::ABAQUS_VTK_FIELDOUTPUTS_MAP(fldOutput)].push_back((fldName + sp.description()).CStr());
	}
}

void odb2vtk::WriteDataArray(
	const odb_FieldOutput& fldOutput,
	const odb_String& description,
	const GLOBAL::OutputDataType& outputDatatype,
	const odb_Enum::odb_ResultPositionEnum& pos,
	int maxNumOfIntegrationPoints,
	std::string& o_buffer)
{
	auto abqComponentLabels = fldOutput.componentLabels();
	// C++ API is different from Python API
	// In Python componentLabels() retrun 1 but C++ returns 0
	int componentsSize = abqComponentLabels.Length() == 0 ? 1 : abqComponentLabels.Length();
	o_buffer += "<DataArray type=\"Float32\" Name=\"" + std::string(description.cStr()) + "\"" + " NumberOfComponents=\"" 
		+ std::to_string(componentsSize * maxNumOfIntegrationPoints) + "\"";
	// use the same component label from Abaqus
	for (int j = 0; j < maxNumOfIntegrationPoints; j++)
	{
		for (int i = 0; i < componentsSize; i++)
		{
			const char* name = abqComponentLabels.Length() == 0 ? "Value" : abqComponentLabels[i].cStr();
			o_buffer += " ComponentName" + std::to_string(i + j * componentsSize) + "=\"" + std::string(name) + "\"";
		}
	}
	o_buffer += " format=\"ascii\">\n";
	
	// use scientific formatting
	std::stringstream s;
	s << std::scientific;
	if (outputDatatype == GLOBAL::OutputDataType::PointData)
	{
		double* data = new double[m_nodesNum * componentsSize];
		memset(data, 0, sizeof(double) * m_nodesNum * componentsSize);
		for (const auto& instanceName : m_instanceNames)
		{
			auto selectedInstance =  m_odb->rootAssembly().instances().constGet(instanceName.c_str());
			auto subset = fldOutput.getSubset(selectedInstance).getSubset(pos);
			this->WriteSortedPointData(subset.bulkDataBlocks(), instanceName, componentsSize, data);
		}
		for (int i = 0; i < m_nodesNum; i++)
		{
			for (int j = 0; j < componentsSize; j++)
			{
				//o_buffer += std::to_string(data[j + componentsSize * i]) + " ";
				s << data[j + componentsSize * i] << " ";
			}
			s << "\n";
			//o_buffer += "\n";
		}
		delete[] data;
	}
	else if (outputDatatype == GLOBAL::OutputDataType::CellData)
	{
		double* data = new double[m_cellsNum * componentsSize * maxNumOfIntegrationPoints];
		memset(data, 0, sizeof(double) * m_cellsNum * componentsSize * maxNumOfIntegrationPoints);
		for (const auto& instanceName : m_instanceNames)
		{
			auto selectedInstance = m_odb->rootAssembly().instances().constGet(instanceName.c_str());
			auto subset = fldOutput.getSubset(selectedInstance).getSubset(pos);
			this->WriteSortedCellData(subset.bulkDataBlocks(), instanceName, data);
		}
		for (int i = 0; i < m_cellsNum; i++)
		{
			for (int j = 0; j < componentsSize * maxNumOfIntegrationPoints; j++)
			{
				s << data[j + componentsSize * maxNumOfIntegrationPoints * i] << " ";
				//o_buffer += std::to_string(data[j + componentsSize * maxNumOfIntegrationPoints * i]) + " ";
			}
			s << "\n";
			//o_buffer += "\n";
		}
		delete[] data;
	}

	o_buffer += s.str();
	o_buffer += "</DataArray>";
	o_buffer += "\n";
}

void odb2vtk::WriteSortedPointData(const odb_SequenceFieldBulkData& blkDataBlock,
	const std::string& instanceName,
	const int& componentsSize,
	double* o_data)
{
	for (int i = 0; i < blkDataBlock.size(); i++)
	{
		auto blk = blkDataBlock[i];
		int numNodes = blk.length();
		int numComp = blk.width();
		float* data = blk.data();
		for (int j = 0; j < numNodes; j++)
		{
			int nodeLabelAbq = blk.nodeLabels()[j];
			INT64 nodeLabelVtk = m_nodesMap[instanceName][nodeLabelAbq];
			for (int comp = 0; comp < numComp; comp++)
			{
				o_data[nodeLabelVtk * numComp + comp] = data[j * numComp + comp];
			}
		}
	}
}

void odb2vtk::WriteSortedCellData(const odb_SequenceFieldBulkData& blkDataBlock,
	const std::string& instanceName, 
	double* o_data)
{
	for (int i = 0; i < blkDataBlock.size(); i++)
	{
		auto blk = blkDataBlock[i];
		int numValues = blk.length();
		int numComp = blk.width();
		int nElems = blk.numberOfElements();
		int numIP = numValues / nElems;
		float* data = blk.data();
		for (int j = 0; j < nElems; j++)
		{
			int cellLabelAbq = blk.elementLabels()[j];
			INT64 cellLabelVtk = m_cellsMap[instanceName][cellLabelAbq];
			for (int ip = 0; ip < numIP; ip++) 
			{
				for (int comp = 0; comp < numComp; comp++)
				{
					o_data[cellLabelVtk * numComp * numIP + (INT64)ip * (INT64)numComp + comp] =
						data[j * numComp * numIP + ip * numComp + comp];
				}
			}
		}
	}
}

void odb2vtk::WriteLocalCS(std::string fldName, 
	const char* stepName, 
	int frameIdx, 
	std::map<std::string, std::vector<std::string>>& o_dataMap, 
	std::string& o_buffer)
{
	o_buffer += "<DataArray type=\"Float32\" Name=\"" + 
		fldName + "\"" + " NumberOfComponents=\"3\"" + " format=\"ascii\">\n";
	// local orientation is retrived from "S" stress fieldoutput
	auto fldOutput = m_odb->steps()[stepName].frames()[frameIdx].fieldOutputs().constGet("S");

	float* data = new float[m_cellsNum * 3];
	for (const auto& inst_name : m_instanceNames)
	{
		auto inst = m_odb->rootAssembly().instances()[inst_name.c_str()];
		auto instStress = fldOutput
			.getSubset(inst)
			.getSubset(odb_Enum::odb_ResultPositionEnum::CENTROID);
		for (int i = 0; i < instStress.bulkDataBlocks().size(); i++)
		{
			auto block = instStress.bulkDataBlocks()[i];
			// local coordinate system is a quaternion.
			// size is 4 x numElements
			float* localCS = block.localCoordSystem();
			if (localCS == nullptr)
			{
				for (int elem = 0; elem < block.numberOfElements(); elem++)
				{
					int abqIndex = block.elementLabels()[elem];
					int vtkIndex = m_cellsMap[inst_name][abqIndex];
					data[vtkIndex * 3] = 1; // default orientation if localCS is empty
					data[vtkIndex * 3 + 1] = 0;
					data[vtkIndex * 3 + 2] = 0;
				}
			}
			else 
			{
				for (int elem = 0; elem < block.numberOfElements(); elem++)
				{
					int abqIndex = block.elementLabels()[elem];
					int vtkIndex = m_cellsMap[inst_name][abqIndex];
					float q1 = localCS[elem * 4];
					float q2 = localCS[elem * 4 + 1];
					float q3 = localCS[elem * 4 + 2];
					float q4 = localCS[elem * 4 + 3]; // scalar term
					data[vtkIndex * 3] = q4 * q4 + q1 * q1 - q2 * q2 - q3 * q3; 
					data[vtkIndex * 3 + 1] = 2 * (q1 * q2 - q3 * q4);
					data[vtkIndex * 3 + 2] = 2 * (q1 * q3 + q2 * q4);
					//float x = q4 * q4 + q1 * q1 - q2 * q2 - q3 * q3;
					//float y = 2 * (q1 * q2 - q3 * q4);
					//float z = 2 * (q1 * q3 + q2 * q4);
					//o_buffer += "\"" + std::to_string(x) + " " + std::to_string(y) + " " + std::to_string(z) + "\"";
				}
				//o_buffer += "\n";
			}
		}
	}

	for (int i = 0; i < m_cellsNum; i++)
	{
		o_buffer += std::to_string(data[i * 3]) + " " 
			+ std::to_string(data[i * 3 + 1]) + " "
			+ std::to_string(data[i * 3 + 2]);
		o_buffer += "\n";
	}

	o_buffer += "</DataArray>";
	o_buffer += "\n";

	// add vectors for localCS in the XML header
	o_dataMap["Vectors"].push_back(fldName);

	delete[] data;
}

void odb2vtk::WriteVTUFiles()
{
	// only call constructmap once.
	this->ConstructMap();
	for (auto const& item : m_stepFrameMap)
	{
		for (auto const& frameIdx : item.second)
		{
			this->WriteVTUFile(item.first, frameIdx);
		}
	}
}

void odb2vtk::WriteVTUFile(std::string stepName, int frameIdx)
{
	if (m_odb != nullptr)
	{
		// naming convention is odbname_stepname_framenumber.vtu
		auto filename = m_odbPath + "/" 
			+ m_odbBaseName.substr(0, m_odbBaseName.size() - 4)
			+ "_" + stepName
			+ "_" + std::to_string(frameIdx)
			+ ".vtu";
		std::ofstream vtu(filename);
		if (vtu.is_open())
		{
			// start writing the buffer
			vtu << "<VTKFile type = \"UnstructuredGrid\" version = \"1,0\" byte_order = \"LittleEndian\">" << "\n";
			vtu << "<UnstructuredGrid>" << "\n";
			vtu << "<Piece NumberOfPoints=\"" << m_nodesNum << "\" " << "NumberOfCells=\"" << m_cellsNum << "\">" << "\n";
			vtu << "<Points>" << "\n";
			vtu << "<DataArray type=\"Float64\" NumberOfComponents=\"3\" format=\"ascii\">" << "\n";
			
			std::string nodeCoord = "";
			std::string cellConnectivity = "";
			int nodesNumCell = 0;
			int offset = 0;
			std::string cellOffset = "";
			std::string cellType = "";
			auto rootAssy = m_odb->rootAssembly();
			for (const auto& inst_name : m_instanceNames)
			{
				auto inst = rootAssy.instances()[inst_name.c_str()];
				// write node coordinates
				for (int i = 0; i < inst.nodes().size(); i++)
				{
					auto node = inst.nodes()[i];
					auto coord = node.coordinates();
					nodeCoord += std::to_string(coord[0]) + " " 
						+ std::to_string(coord[1]) + " " 
						+ std::to_string(coord[2]) + "\n";
				}
				// write cell connectivity, offset, and type
				for (int i = 0; i < inst.elements().size(); i++)
				{
					auto cell = inst.elements()[i];
					// connectivity
					const int* conn = cell.connectivity(nodesNumCell);
					for (int j = 0; j < nodesNumCell; j++)
					{
						cellConnectivity += std::to_string(m_nodesMap[inst_name][conn[j]]) + " ";
					}
					cellConnectivity += "\n";
					// offset
					offset += nodesNumCell;
					cellOffset += std::to_string(offset) + "\n";
					// type
					cellType += std::to_string(GLOBAL::ABAQUS_VTK_CELL_MAP(cell.type().cStr())) + "\n";
				}
			}
			std::cout << "write nodes" << std::endl;
			vtu << nodeCoord;
			vtu << "</DataArray>" << "\n";
			vtu << "</Points>" << "\n";

			// write field data
			std::map<std::string, std::vector<std::string>> pointdataMap, celldataMap;
			pointdataMap["Tensors"] = std::vector<std::string>();
			pointdataMap["Vectors"] = std::vector<std::string>();
			pointdataMap["Scalars"] = std::vector<std::string>();
			celldataMap["Tensors"] = std::vector<std::string>();
			celldataMap["Vectors"] = std::vector<std::string>();
			celldataMap["Scalars"] = std::vector<std::string>();
			std::string bufferPointdataArray, bufferCelldataArray;
			this->WriteFieldOutputData(stepName.c_str(), frameIdx, 
				pointdataMap, celldataMap,
				bufferPointdataArray, bufferCelldataArray);
			
			// add localCS
			this->WriteLocalCS("Material_Orientation", stepName.c_str(), frameIdx, celldataMap, bufferCelldataArray);
			
			// pointdata - e.g., U, RF
			// write pointdata headers
			std::cout << "write pointdata" << std::endl;
			vtu << "<PointData";
			for (const auto& item : pointdataMap)
			{
				if (item.second.size() != 0)
				{
					vtu << " " << item.first << "=" << "\"" << item.second[0];
					for (int i = 1; i < item.second.size(); i++)
					{
						vtu << "," << item.second[i];
					}
					vtu << "\"";
				}
			}
			vtu << ">" << "\n";
			// write pointdata
			vtu << bufferPointdataArray;
			vtu << "</PointData>" << "\n";

			// celldata - e.g., S, E
			// write celldata header
			std::cout << "write celldata" << std::endl;
			vtu << "<CellData ";
			for (const auto& item : celldataMap)
			{
				if (item.second.size() != 0)
				{
					vtu << " " << item.first << "=" << "\"" << item.second[0];
					for (int i = 1; i < item.second.size(); i++)
					{
						vtu << "," << item.second[i];
					}
					vtu << "\"";
				}
			}
			vtu << ">" << "\n";
			// write celldata
			vtu << bufferCelldataArray;
			vtu << "</CellData>" << "\n";

			// write cells
			std::cout << "write cell connectivity, offsets, and types" << std::endl;
			vtu << "<Cells>" << "\n";
			vtu << "<DataArray type=\"Int64\" Name=\"connectivity\" format=\"ascii\">" << "\n";
			vtu << cellConnectivity;
			vtu << "</DataArray>" << "\n";

			vtu << "<DataArray type=\"Int64\" Name=\"offsets\" format=\"ascii\">" << "\n";
			vtu << cellOffset;
			vtu << "</DataArray>" << "\n";

			vtu << "<DataArray type=\"Int64\" Name=\"types\" format=\"ascii\">" << "\n";
			vtu << cellType;
			vtu << "</DataArray>" << "\n";

			vtu << "</Cells>" << "\n";
			vtu << "</Piece>" << "\n";
			vtu << "</UnstructuredGrid>" << "\n";
			vtu << "</VTKFile>";

			std::cout << "complete" << std::endl;

			// write instances 
			//odb_InstanceRepositoryIT instIter(m_odb->rootAssembly().instances());
			//header << "instances: ";
			//for (instIter.first(); !instIter.isDone(); instIter.next())
			//{
			//	header << instIter.currentKey().CStr() << " ";
			//}
			//header << "\n";
			//// write steps and frames
			//odb_StepRepositoryIT stepIter(m_odb->steps());
			//for (stepIter.first(); !stepIter.isDone(); stepIter.next())
			//{
			//	header << stepIter.currentKey().CStr() << ": ";
			//	for (int i = 0; i < stepIter.currentValue().frames().size(); i++)
			//	{
			//		header << i << " ";
			//	}
			//	header << "\n";
			//}
		}
	}
}
