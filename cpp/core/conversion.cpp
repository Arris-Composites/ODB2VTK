#include "odb2vtk_core/conversion.hpp"
#include "odb2vtk_core/mesh.hpp"
#include "profiling.hpp"
#include <algorithm>
#include <limits>
#include <unordered_set>

namespace odb2vtk_core {
void LabelLookup::add(Label label, std::size_t row) {
  if (!rows_.emplace(label, row).second)
    throw SourceError("Duplicate mesh label: " + std::to_string(label));
}
std::size_t LabelLookup::row(Label label) const {
  auto found = rows_.find(label);
  if (found == rows_.end())
    throw SourceError("Unknown mesh label: " + std::to_string(label));
  return found->second;
}
std::vector<std::size_t>
LabelLookup::rows(const std::vector<Label> &labels) const {
  std::vector<std::size_t> result;
  result.reserve(labels.size());
  for (auto label : labels)
    result.push_back(row(label));
  return result;
}
namespace {
std::int64_t vtk_index(std::size_t value) {
  if (value >
      static_cast<std::size_t>(std::numeric_limits<std::int64_t>::max()))
    throw SourceError("VTK index exceeds signed 64-bit range");
  return static_cast<std::int64_t>(value);
}
} // namespace
PreparedMesh prepare_mesh(const std::vector<InstanceMesh> &instances) {
  PreparedMesh result;
  std::size_t nodes = 0, cells = 0;
  std::unordered_set<std::string> names;
  for (const auto &instance : instances) {
    if (instance.name.empty() || !names.insert(instance.name).second)
      throw SourceError("Invalid mesh instance identity");
    if (instance.coordinates.rows() != instance.node_labels.size() ||
        instance.coordinates.columns() != 3)
      throw SourceError("Mesh coordinates and labels disagree");
    LabelLookup node_map, element_map;
    for (auto label : instance.node_labels) {
      node_map.add(label, nodes);
      nodes = detail::sum(nodes, 1);
    }
    for (const auto &element : instance.elements) {
      element_map.add(element.label, cells);
      cells = detail::sum(cells, 1);
    }
    vtk_index(nodes);
    vtk_index(cells);
    result.nodes.emplace(instance.name, std::move(node_map));
    result.elements.emplace(instance.name, std::move(element_map));
  }
  result.geometry.points = Matrix(nodes, 3);
  std::size_t row = 0;
  for (const auto &instance : instances) {
    for (std::size_t i = 0; i < instance.coordinates.rows(); ++i, ++row)
      for (std::size_t c = 0; c < 3; ++c)
        result.geometry.points(row, c) = instance.coordinates(i, c);
    const auto &lookup = result.nodes.at(instance.name);
    for (const auto &element : instance.elements) {
      for (auto label : element.connectivity)
        result.geometry.connectivity.push_back(vtk_index(lookup.row(label)));
      result.geometry.offsets.push_back(
          vtk_index(result.geometry.connectivity.size()));
      try {
        result.geometry.cell_types.push_back(vtk_cell_type(element.type));
      } catch (const std::invalid_argument &error) {
        throw SourceError(error.what());
      }
    }
  }
  return result;
}
void place_points(const FieldBlock &block, const LabelLookup &lookup,
                  Matrix &output) {
  detail::PhaseScope timing(detail::Phase::field_assembly);
  if (block.labels.size() != block.values.rows() ||
      block.values.columns() != output.columns())
    throw SourceError("Point field shape mismatch");
  const auto rows = lookup.rows(block.labels);
  for (auto row : rows)
    if (row >= output.rows())
      throw SourceError("Point row out of range");
  for (std::size_t i = 0; i < rows.size(); ++i)
    for (std::size_t c = 0; c < output.columns(); ++c)
      output(rows[i], c) = block.values(i, c);
}
void place_cells(const FieldBlock &block, const LabelLookup &lookup,
                 Matrix &output) {
  detail::PhaseScope timing(detail::Phase::field_assembly);
  if (block.position != "INTEGRATION_POINT" &&
      block.integration_points.empty()) {
    place_points(block, lookup, output);
    return;
  }
  const auto width = block.values.columns();
  if (!width || block.values.rows() != block.labels.size() ||
      block.integration_points.size() != block.labels.size() ||
      output.columns() % width)
    throw SourceError("Integration-point field shape mismatch");
  const auto rows = lookup.rows(block.labels);
  for (std::size_t i = 0; i < rows.size(); ++i)
    if (rows[i] >= output.rows() || block.integration_points[i] < 1 ||
        static_cast<std::uint64_t>(block.integration_points[i]) >
            output.columns() / width)
      throw SourceError(
          "Integration-point row or component slice out of range");
  for (std::size_t i = 0; i < rows.size(); ++i) {
    const auto start =
        (static_cast<std::size_t>(block.integration_points[i]) - 1) * width;
    for (std::size_t c = 0; c < width; ++c)
      output(rows[i], start + c) = block.values(i, c);
  }
}
Matrix quaternion_directions(const Matrix &q) {
  if (q.columns() != 4)
    throw SourceError("Quaternions require four padded components");
  Matrix output(q.rows(), 3);
  for (std::size_t i = 0; i < q.rows(); ++i) {
    const double a = q(i, 0), b = q(i, 1), c = q(i, 2), d = q(i, 3);
    output(i, 0) = d * d + a * a - b * b - c * c;
    output(i, 1) = 2 * (a * b - c * d);
    output(i, 2) = 2 * (a * c + b * d);
  }
  return output;
}
HistoryTable assemble_history(const std::vector<HistorySeries> &series) {
  std::size_t rows = 0;
  for (const auto &item : series) {
    if (item.timestamps.size() != item.values.size())
      throw SourceError("History time/value lengths disagree");
    rows = std::max(rows, item.values.size());
  }
  HistoryTable result{{}, Matrix(rows, series.size())};
  for (std::size_t column = 0; column < series.size(); ++column) {
    result.headers.push_back(series[column].name);
    for (std::size_t row = 0; row < series[column].values.size(); ++row)
      result.values(row, column) = series[column].values[row];
  }
  return result;
}
} // namespace odb2vtk_core
