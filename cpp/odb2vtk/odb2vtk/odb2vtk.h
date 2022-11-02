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
	odb2vtk(const char* odb_fullname, const char* suffix);
	~odb2vtk();

	/// <summary>
	/// Write a json file consisting of instance name, step, and frames.
	/// </summary>
	void ExtractHeader();
	/// <summary>
	/// Copy selected instances and frames to object.
	/// </summary>
	/// <param name="instance_names">selected instance names</param>
	/// <param name="step_frame_map">selected frames</param>
	void ReadArgs(const std::vector<std::string>& instance_names, 
		const std::map<std::string, std::vector<int>>& step_frame_map);
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
	/// <param name="step_name">request step</param>
	/// <param name="frame_idx">request frame</param>
	void WriteVTUFile(std::string step_name, int frame_idx);
	/// <summary>
	/// Build the containers for mapping from Abaqus to VTK.
	/// </summary>
	void ConstructMap();

	/// <param name="o_celldata_array"></param>
	void WriteFieldOutputData(
		const char* step_name,
		int frame_idx,
		std::map<std::string, std::vector<std::string>>& o_pointdata_map,
		std::map<std::string, std::vector<std::string>>& o_celldata_map,
		std::string& o_pointdata_array, 
		std::string& o_celldata_array);

	void WriteDataArrayWithSectionPoints(
		const std::vector<odb_SectionPoint>& section_points,
		const odb_FieldOutput& fld_output,
		const odb_Enum::odb_ResultPositionEnum& pos,
		const odb_String& fld_name,
		int maxNumOfIntegrationPoints,
		const GLOBAL::OutputDataType& output_datatype,
		std::map<std::string, std::vector<std::string>>& o_data_map,
		std::string& o_buffer);

	void WriteDataArray(
		const odb_FieldOutput& fld_output, 
		const odb_String& description, 
		const GLOBAL::OutputDataType& output_datatype,
		const odb_Enum::odb_ResultPositionEnum& pos,
		int maxNumOfIntegrationPoints,
		std::string& o_buffer);

	void WriteSortedPointData(
		const odb_SequenceFieldBulkData& blk_data_block,
		const std::string& instance_name,
		const int& components_size,
		double* o_data);

	void WriteSortedCellData(
		const odb_SequenceFieldBulkData& blk_data_block,
		const std::string& instance_name,
		double* o_data);
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

