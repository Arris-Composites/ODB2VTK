#/*=========================================================================
#    Program: ODB2VTK
#    Module:  main.cpp
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

#include "odb2vtk_core/abaqus_source.hpp"
#include "odb2vtk_core/cli.hpp"
#include <iostream>

namespace {
int run(const std::vector<std::string>& arguments) {
  return odb2vtk_core::cli_main(arguments,
      [](const std::filesystem::path& path) -> std::unique_ptr<odb2vtk_core::Source> {
        return std::make_unique<odb2vtk_core::AbaqusSource>(path.string());
      }, std::cout, std::cerr);
}
}
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
  std::vector<std::string> arguments;
  for (int i=1; i<argc; ++i) arguments.push_back(std::filesystem::path(argv[i]).u8string());
  return run(arguments);
}
#else
int main(int argc, char** argv) {
  return run(std::vector<std::string>(argv+1, argv+argc));
}
#endif
