#pragma once
#include "models.hpp"
#include <unordered_map>

namespace odb2vtk_core {
class LabelLookup {
public:
  void add(Label label, std::size_t row);
  std::size_t row(Label label) const;
  std::vector<std::size_t> rows(const std::vector<Label>& labels) const;
private:
  std::unordered_map<Label, std::size_t> rows_;
};
struct PreparedMesh {
  MeshData geometry;
  std::unordered_map<std::string, LabelLookup> nodes, elements;
};
PreparedMesh prepare_mesh(const std::vector<InstanceMesh>& instances);
void place_points(const FieldBlock& block, const LabelLookup& lookup, Matrix& output);
void place_cells(const FieldBlock& block, const LabelLookup& lookup, Matrix& output);
Matrix quaternion_directions(const Matrix& quaternions);
HistoryTable assemble_history(const std::vector<HistorySeries>& series);
}
