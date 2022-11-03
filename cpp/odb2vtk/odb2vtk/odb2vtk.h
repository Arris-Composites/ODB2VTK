#pragma once
#include <string>
#include <odb_API.h>   
#include <map>
#include <vector>

namespace GLOBAL {
	enum OutputDataType;
};

class odb2vtk
{
public:
	odb2vtk(const char* odbFullname, const char* suffix);
	~odb2vtk();

	/// <summary>
	/// Write a json file consisting of instance name, step, and frames.
	/// </summary>
	void ExtractHeader();

	/// <summary>
	/// Copy selected instances and frames to object.
	/// </summary>
	/// <param name="instanceNames">selected instance names</param>
	/// <param name="stepFrameMap">selected frames</param>
	void ReadArgs(const std::vector<std::string>& instanceNames, 
		const std::map<std::string, std::vector<int>>& stepFrameMap);

	/// <summary>
	/// Write CSV file for history data.
	/// </summary>
	void WriteCSVFile();

	/// <summary>
	/// Write one PVD file.
	/// </summary>
	void WritePVDFile();

	/// <summary>
	/// Write VTU files.
	/// </summary>
	void WriteVTUFiles();

private:
	/// <summary>
	/// Write one VTU file for a specific step and frame.
	/// </summary>
	/// <param name="stepName">request step</param>
	/// <param name="frameIdx">request frame</param>
	void WriteVTUFile(std::string stepName, int frameIdx);

	/// <summary>
	/// Build the containers for mapping from Abaqus to VTK.
	/// </summary>
	void ConstructMap();

	/// <summary>
	/// Write fieldoutput for a specific step and frame.
	/// This function will fill in the map and data array which is a string to be written to file.
	/// </summary>
	/// <param name="stepName"></param>
	/// <param name="frameIdx"></param>
	/// <param name="o_pointdataMap"></param>
	/// <param name="o_celldataMap"></param>
	/// <param name="o_pointdataArray"></param>
	/// <param name="o_celldataArray"></param>
	void WriteFieldOutputData(
		const char* stepName,
		int frameIdx,
		std::map<std::string, std::vector<std::string>>& o_pointdataMap,
		std::map<std::string, std::vector<std::string>>& o_celldataMap,
		std::string& o_pointdataArray, 
		std::string& o_celldataArray);

	/// <summary>
	/// Write data array for section points.
	/// If there is not section points, write as one array.
	/// </summary>
	/// <param name="sectionPoints"></param>
	/// <param name="fldOutput"></param>
	/// <param name="pos"></param>
	/// <param name="fldName"></param>
	/// <param name="maxNumOfIntegrationPoints"></param>
	/// <param name="outputDatatype"></param>
	/// <param name="o_dataMap"></param>
	/// <param name="o_buffer"></param>
	void WriteDataArrayWithSectionPoints(
		const std::vector<odb_SectionPoint>& sectionPoints,
		const odb_FieldOutput& fldOutput,
		const odb_Enum::odb_ResultPositionEnum& pos,
		const odb_String& fldName,
		int maxNumOfIntegrationPoints,
		const GLOBAL::OutputDataType& outputDatatype,
		std::map<std::string, std::vector<std::string>>& o_dataMap,
		std::string& o_buffer);

	/// <summary>
	/// Write data array.
	/// </summary>
	/// <param name="fldOutput"></param>
	/// <param name="description"></param>
	/// <param name="outputDatatype"></param>
	/// <param name="pos"></param>
	/// <param name="maxNumOfIntegrationPoints"></param>
	/// <param name="o_buffer"></param>
	void WriteDataArray(
		const odb_FieldOutput& fldOutput, 
		const odb_String& description, 
		const GLOBAL::OutputDataType& outputDatatype,
		const odb_Enum::odb_ResultPositionEnum& pos,
		int maxNumOfIntegrationPoints,
		std::string& o_buffer);

	void WriteSortedPointData(
		const odb_SequenceFieldBulkData& blkDataBlock,
		const std::string& instanceName,
		const int& components_size,
		double* o_data);

	void WriteSortedCellData(
		const odb_SequenceFieldBulkData& blkDataBlock,
		const std::string& instanceName,
		double* o_data);

	void WriteLocalCS(
		std::string fldName,
		const char* stepName,
		int frameIdx,
		std::map<std::string, std::vector<std::string>>& o_dataMap,
		std::string& o_buffer);

private:
	std::string m_odbFullName;
	std::string m_odbPath;
	std::string m_odbBaseName;
	odb_Odb* m_odb;
	std::map<std::string, std::map<int, int>> m_nodesMap;
	std::map<std::string, std::map<int, int>> m_cellsMap;
	std::map<std::string, std::vector<int>> m_stepFrameMap;
	std::vector<std::string> m_instanceNames;
	size_t m_nodesNum;
	size_t m_cellsNum;
	
};

