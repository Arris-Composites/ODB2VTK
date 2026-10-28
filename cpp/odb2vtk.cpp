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
#include "odb2vtk_core/exporter.hpp"
#include <iostream>

odb2vtk::odb2vtk(const char* path, const char* suffix)
    : outputs_(odb2vtk_core::OutputOptions::from_odb(path, suffix ? suffix : "")) {
  source_=std::make_unique<odb2vtk_core::AbaqusSource>(path);
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
  odb2vtk_core::Exporter(*source_).export_header(outputs_);
}
void odb2vtk::WriteVTUFiles() {
  if (!selection_) throw odb2vtk_core::SelectionError("Provide a complete selection before export");
  odb2vtk_core::Exporter exporter(*source_, [](const odb2vtk_core::ProgressEvent& event) {
    std::cout << "Completed: " << event.path.u8string() << '\n';
  });
  const auto result=exporter.export_frames(*selection_,outputs_);
  for (const auto& diagnostic : result.diagnostics)
    std::cout << "Omitted " << diagnostic.field << ": " << diagnostic.message << '\n';
}
void odb2vtk::WriteCSVFile() {
  if (!selection_) throw odb2vtk_core::SelectionError("Provide a selection before history export");
  odb2vtk_core::Exporter(*source_).export_history(*selection_,outputs_);
}
void odb2vtk::WritePVDFile() {
  if (!selection_) throw odb2vtk_core::SelectionError("Provide a selection before collection export");
  odb2vtk_core::Exporter(*source_).export_collection(*selection_,outputs_);
}
