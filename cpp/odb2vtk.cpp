#/*=========================================================================
#    Program: ODB2VTK
#    Module:  odb2vtk.cpp
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

#include "odb2vtk.h"
#include "odb2vtk_core/abaqus_source.hpp"
#include "odb2vtk_core/converter.hpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>

namespace {
using namespace odb2vtk_core;
class LegacyWriter final : public FrameSink {
public:
  LegacyWriter(std::string directory,std::string name)
      : directory_(std::move(directory)), name_(std::move(name)) {}
  void begin_frame(const FrameInfo& info,const MeshData& mesh,
                   const std::vector<FieldMetadata>& metadata) override {
    frame_=info; mesh_=&mesh; metadata_=metadata; points_.clear(); cells_.clear();
  }
  void field(const FieldArray& field) override {
    const auto& meta=field.metadata;
    std::ostringstream text;
    text << "<DataArray type=\"Float32\" Name=\"" << meta.name
         << "\" NumberOfComponents=\"" << meta.width << "\"";
    for (std::size_t i=0; i<meta.components.size(); ++i)
      text << " ComponentName" << i << "=\"" << meta.components[i] << "\"";
    text << " format=\"ascii\">\n" << std::scientific;
    for (std::size_t row=0; row<field.values.rows(); ++row) {
      for (std::size_t c=0; c<field.values.columns(); ++c) {
        if (meta.name=="Material_Orientation") text << std::to_string(field.values(row,c));
        else text << field.values(row,c);
        text << ' ';
      }
      text << '\n';
    }
    text << "</DataArray>\n";
    (meta.association=="PointData" ? points_ : cells_) += text.str();
  }
  void end_frame() override {
    const auto path=std::filesystem::path(directory_)/(name_+"_"+frame_.step+"_"+std::to_string(frame_.index)+".vtu");
    std::ofstream out(path);
    if (!out) throw std::runtime_error("Cannot open output: " + path.string());
    out << "<VTKFile type=\"UnstructuredGrid\" version=\"1,0\" byte_order=\"LittleEndian\">\n"
        << "<UnstructuredGrid>\n<Piece NumberOfPoints=\"" << mesh_->points.rows()
        << "\" NumberOfCells=\"" << mesh_->offsets.size() << "\">\n"
        << "<Points>\n<DataArray type=\"Float64\" NumberOfComponents=\"3\" format=\"ascii\">\n";
    for (std::size_t row=0; row<mesh_->points.rows(); ++row)
      out << std::to_string(mesh_->points(row,0)) << ' ' << std::to_string(mesh_->points(row,1))
          << ' ' << std::to_string(mesh_->points(row,2)) << '\n';
    out << "</DataArray>\n</Points>\n";
    association(out,"PointData",points_); association(out,"CellData",cells_);
    out << "<Cells>\n";
    const std::vector<std::int64_t>* arrays[]={&mesh_->connectivity,&mesh_->offsets,&mesh_->cell_types};
    const char* names[]={"connectivity","offsets","types"};
    for (int i=0; i<3; ++i) {
      out << "<DataArray type=\"Int64\" Name=\"" << names[i] << "\" format=\"ascii\">\n";
      for (auto value : *arrays[i]) out << value << '\n';
      out << "</DataArray>\n";
    }
    out << "</Cells>\n</Piece>\n</UnstructuredGrid>\n</VTKFile>";
    out.close();
    if (!out) throw std::runtime_error("Cannot complete output: " + path.string());
    mesh_=nullptr;
    std::cout << "Completed: " << path.string() << '\n';
  }
private:
  void association(std::ostream& out,const std::string& association,const std::string& text) {
    // Retain legacy metadata/format policy until Phase 3 writer replacement.
    std::map<std::string,std::vector<std::string>> names;
    for (const auto& field : metadata_)
      if (field.association==association) names[field.kind].push_back(field.name);
    out << '<' << association;
    for (const auto& kind : names) {
      out << ' ' << kind.first << "=\"";
      for (std::size_t i=0; i<kind.second.size(); ++i) out << (i ? "," : "") << kind.second[i];
      out << '"';
    }
    out << ">\n" << text << "</" << association << ">\n";
  }
  std::string directory_, name_, points_, cells_;
  FrameInfo frame_;
  const MeshData* mesh_=nullptr;
  std::vector<FieldMetadata> metadata_;
};
}

odb2vtk::odb2vtk(const char* path,const char*) {
  const auto file=std::filesystem::absolute(std::filesystem::path(path));
  directory_=file.parent_path().string(); name_=file.stem().string();
  source_=std::make_unique<odb2vtk_core::AbaqusSource>(file.string());
}
odb2vtk::~odb2vtk() = default;
void odb2vtk::ReadArgs(const std::vector<std::string>& instances,
    const std::map<std::string,std::vector<int>>& steps) {
  std::vector<odb2vtk_core::StepSelection> selected;
  for (const auto& step : steps)
    selected.push_back({step.first,std::vector<std::int64_t>(step.second.begin(),step.second.end())});
  selection_.emplace(instances,std::move(selected));
}
void odb2vtk::ExtractHeader() {
  const auto file=std::filesystem::path(directory_)/"header.txt";
  std::ofstream out(file);
  if (!out) throw std::runtime_error("Cannot open header: " + file.string());
  out << "instances: ";
  for (const auto& name : source_->instance_names()) out << name << ' ';
  out << '\n';
  for (const auto& step : source_->steps()) {
    out << step.name << ": ";
    for (std::size_t frame=0; frame<step.frame_count; ++frame) out << frame << ' ';
    out << '\n';
  }
  out.close();
  if (!out) throw std::runtime_error("Cannot complete header: " + file.string());
}
void odb2vtk::WriteVTUFiles() {
  if (!selection_) throw odb2vtk_core::SelectionError("Provide a complete selection before export");
  LegacyWriter writer(directory_,name_);
  odb2vtk_core::Converter converter(*source_);
  const auto result=converter.convert(*selection_,writer);
  for (const auto& diagnostic : result.diagnostics)
    std::cout << "Omitted " << diagnostic.field << ": " << diagnostic.message << '\n';
}
void odb2vtk::WriteCSVFile() {}
void odb2vtk::WritePVDFile() {}
