#include "odb2vtk_core/mesh.hpp"
#include <stdexcept>

namespace odb2vtk_core {
int vtk_cell_type(const std::string& element_type) {
  static const struct { const char* family; int vtk_type; } types[] = {
      {"C3D4", 10}, {"C3D6", 13}, {"C3D8", 12}, {"C3D10", 24},
      {"C3D15", 26}, {"C3D20", 25}, {"S3", 5}, {"S4", 9}, {"S8", 23},
      {"S9", 28}, {"B31", 3}, {"R3D3", 5}, {"R3D4", 9}};
  for (const auto& type : types) {
    if (element_type.find(type.family) != std::string::npos) return type.vtk_type;
  }
  throw std::invalid_argument(element_type + " element type not found");
}
}
