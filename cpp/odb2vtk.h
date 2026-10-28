#/*=========================================================================
#    Program: ODB2VTK
#    Module:  odb2vtk.h
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

#pragma once
#include "odb2vtk_core/source.hpp"
#include "odb2vtk_core/outputs.hpp"
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

// Temporary CLI adapter. Conversion and publication use the maintained core.
class odb2vtk {
public:
  odb2vtk(const char* path,const char* suffix);
  ~odb2vtk();
  odb2vtk(const odb2vtk&) = delete;
  odb2vtk& operator=(const odb2vtk&) = delete;
  void ExtractHeader();
  void ReadArgs(const std::vector<std::string>&,
                const std::map<std::string,std::vector<int>>&);
  void WriteVTUFiles();
  void WriteCSVFile();
  void WritePVDFile();
private:
  std::unique_ptr<odb2vtk_core::Source> source_;
  std::optional<odb2vtk_core::Selection> selection_;
  odb2vtk_core::OutputOptions outputs_;
};
