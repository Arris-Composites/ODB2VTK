#include "odb2vtk_core/mesh.hpp"
#include <iostream>
#include <stdexcept>
#include <string>

int main() {
  const struct { const char* name; int expected; } cases[] = {
      {"C3D4H", 10}, {"C3D6", 13}, {"C3D8R", 12}, {"C3D10M", 24},
      {"C3D15", 26}, {"C3D20R", 25}, {"S3R", 5}, {"S4R", 9}, {"S8R", 23},
      {"S9R5", 28}, {"B31", 3}, {"R3D3", 5}, {"R3D4", 9},
      {"prefix-C3D8R", 12}, {"C3D4-C3D8", 10}};
  for (const auto& item : cases) {
    if (odb2vtk_core::vtk_cell_type(item.name) != item.expected) {
      std::cerr << "Incorrect mapping: " << item.name << '\n'; return 1;
    }
  }
  for (const auto& name : {std::string(), std::string("UNKNOWN"), std::string("c3d8")}) {
    try { odb2vtk_core::vtk_cell_type(name); }
    catch (const std::invalid_argument&) { continue; }
    std::cerr << "Unsupported element accepted: " << name << '\n'; return 1;
  }
  std::cout << "18 mesh mapping cases passed\n";
}
