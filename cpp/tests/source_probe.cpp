// Machine-readable numerical/ownership probe, not a production serializer.
#include "odb2vtk_core/abaqus_source.hpp"
#include "odb2vtk_core/converter.hpp"
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <locale>
#include <optional>
#include <sstream>

using namespace odb2vtk_core;
namespace {
std::string quoted(const std::string& value) {
  std::ostringstream out; out << '"';
  for (const unsigned char c : value) {
    if (c=='"' || c=='\\') out << '\\' << c;
    else if (c<32) { const char* hex="0123456789abcdef";out << "\\u00" << hex[c>>4] << hex[c&15]; }
    else out << c;
  }
  return out.str()+'"';
}
void number(double value) {
  if (std::isnan(value)) std::cout << "NaN";
  else if (std::isinf(value)) std::cout << (value>0 ? "Infinity" : "-Infinity");
  else if (value==0 && std::signbit(value)) std::cout << "-0.0";
  else std::cout << value;
}
void matrix(const Matrix& values) {
  std::cout << "{\"shape\":[" << values.rows() << ',' << values.columns() << "],\"values\":[";
  bool first=true;
  for (auto value : values.values()) { if (!first) std::cout << ',';first=false;number(value); }
  std::cout << "]}";
}
template<class Values> void array(const Values& values) {
  std::cout << '[';bool first=true;
  for (const auto& value : values) { if (!first) std::cout << ',';first=false;std::cout << value; }
  std::cout << ']';
}
void strings(const std::vector<std::string>& values) {
  std::cout << '[';bool first=true;
  for (const auto& value : values) { if (!first) std::cout << ',';first=false;std::cout << quoted(value); }
  std::cout << ']';
}
class Probe final : public FrameSink {
public:
  void begin_frame(const FrameInfo& frame,const MeshData& mesh,const std::vector<FieldMetadata>&) override {
    if (!first_frame_) std::cout << ',';first_frame_=false;first_field_=true;
    std::cout << "{\"step\":" << quoted(frame.step) << ",\"frame\":" << frame.index << ",\"time\":";
    number(frame.time);std::cout << ",\"points\":";matrix(mesh.points);
    std::cout << ",\"connectivity\":";array(mesh.connectivity);
    std::cout << ",\"offsets\":";array(mesh.offsets);
    std::cout << ",\"cell_types\":";array(mesh.cell_types);
    std::cout << ",\"fields\":[";
  }
  void field(const FieldArray& field) override {
    if (!first_field_) std::cout << ',';first_field_=false;
    std::cout << "{\"name\":" << quoted(field.metadata.name)
              << ",\"association\":" << quoted(field.metadata.association)
              << ",\"kind\":" << quoted(field.metadata.kind) << ",\"components\":";
    strings(field.metadata.components);std::cout << ",\"values\":";matrix(field.values);std::cout << '}';
  }
  void end_frame() override { std::cout << "]}"; }
private:
  bool first_frame_=true,first_field_=true;
};
}
int main(int argc,char** argv) {
  if (argc<4 || argc>5) { std::cerr << "Usage: odb2vtk_source_probe FILE INSTANCE|* FRAMES [STEP]\n";return 2; }
  try {
    AbaqusSource source(argv[1]);
    AbaqusSource second(argv[1]); // Independent named ODB handles share API lifetime.
    std::vector<std::string> instances;
    if (std::string(argv[2])=="*") instances=source.instance_names();
    else {
      std::istringstream names(argv[2]);std::string name;
      while (std::getline(names,name,',')) instances.push_back(name);
    }
    std::vector<std::int64_t> frames;std::istringstream frame_text(argv[3]);std::string token;
    while (std::getline(frame_text,token,',')) {
      std::size_t used=0;auto index=std::stoll(token,&used);
      if (used!=token.size()) throw SelectionError("Invalid frame list");frames.push_back(index);
    }
    const std::string step=argc==5 ? argv[4] : "Step-1";
    const Selection selection(instances,{{step,frames}});
    auto retained_mesh=source.mesh(instances.at(0));
    std::optional<FieldBlock> retained;
    const auto field_names=source.field_names(step,static_cast<std::size_t>(frames.at(0)));
    for (const auto& name : field_names) {
      auto info=source.describe_field(step,static_cast<std::size_t>(frames[0]),name,instances);
      if (info.layout.position=="NODAL") {
        source.field_blocks(step,static_cast<std::size_t>(frames[0]),name,instances[0],"NODAL",std::nullopt,
          [&](FieldBlock block) { if (!retained) retained.emplace(std::move(block)); });
        break;
      }
    }
    std::cout.imbue(std::locale::classic());std::cout << std::setprecision(17);
    std::cout << "{\"frames\":[";
    Probe probe;Converter converter(source);const auto result=converter.convert(selection,probe);
    std::cout << "],\"history\":{\"headers\":";
    const auto history=converter.history(selection);strings(history.headers);
    std::cout << ",\"values\":";matrix(history.values);std::cout << "},\"diagnostics\":[";
    bool first=true;
    for (const auto& diagnostic : result.diagnostics) {
      if (!first) std::cout << ',';first=false;
      std::cout << quoted(diagnostic.field+": "+diagnostic.message);
    }
    source.close();source.close();
    bool rejected=false;
    try { source.instance_names(); } catch (const SourceError&) { rejected=true; }
    if (!rejected || !source.closed() || second.instance_names().empty()) throw std::runtime_error("Source lifetime failure");
    second.close();
    // All records below are used after both native handles and the API close.
    std::cout << "],\"closed\":true,\"retained_mesh\":";matrix(retained_mesh.coordinates);
    std::cout << ",\"retained_node_labels\":";array(retained_mesh.node_labels);
    std::cout << ",\"retained_block\":";if (retained) matrix(retained->values);else std::cout << "null";
    std::cout << ",\"history_columns\":" << history.headers.size() << "}\n";
    return 0;
  } catch (const std::exception& error) { std::cerr << error.what() << '\n';return 1; }
}
