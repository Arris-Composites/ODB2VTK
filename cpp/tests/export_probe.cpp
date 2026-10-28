#include "odb2vtk_core/abaqus_source.hpp"
#include "odb2vtk_core/exporter.hpp"
#include <iostream>
#include <sstream>

using namespace odb2vtk_core;
int main(int argc, char** argv) {
  if (argc!=6) {
    std::cerr << "Usage: odb2vtk_export_probe ODB DIRECTORY ascii|binary INSTANCE[,INSTANCE] FRAMES\n";
    return 2;
  }
  try {
    const std::string format=argv[3];
    if (format!="ascii" && format!="binary") throw OutputError("Invalid format");
    std::vector<std::string> instances;
    std::vector<std::int64_t> frames;
    std::istringstream names(argv[4]), indices(argv[5]);
    std::string token;
    while (std::getline(names,token,',')) instances.push_back(token);
    while (std::getline(indices,token,',')) frames.push_back(std::stoll(token));
    const auto defaults=OutputOptions::from_odb(argv[1]);
    const OutputOptions options(argv[2],defaults.run_name(),"",true,
                                format=="binary" ? VtuFormat::binary : VtuFormat::ascii);
    const Selection selection(instances,{{"Step-1",frames}});
    AbaqusSource source(argv[1]);
    Exporter exporter(source);
    exporter.export_header(options); exporter.export_history(selection,options);
    const auto result=exporter.export_frames(selection,options);
    exporter.export_collection(selection,options);
    source.close();
    std::cout << result.frames.size() << " frames, JSON, CSV and PVD published; source closed\n";
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
