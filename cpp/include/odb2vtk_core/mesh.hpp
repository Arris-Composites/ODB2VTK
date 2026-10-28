#pragma once
#include <string>

namespace odb2vtk_core {
// Preserve Python's family matching and precedence. Unknown types are errors.
int vtk_cell_type(const std::string &element_type);
} // namespace odb2vtk_core
