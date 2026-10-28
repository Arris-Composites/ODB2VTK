#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace odb2vtk_core {
using Label = std::int64_t;
class SourceError : public std::runtime_error { public: using std::runtime_error::runtime_error; };
class SelectionError : public std::invalid_argument { public: using std::invalid_argument::invalid_argument; };

namespace detail {
std::size_t product(std::size_t a, std::size_t b);
std::size_t sum(std::size_t a, std::size_t b);
}

class Matrix {
public:
  Matrix() = default;
  Matrix(std::size_t rows, std::size_t columns);
  Matrix(std::size_t rows, std::size_t columns, std::vector<double> values);
  Matrix(const Matrix&) = default;
  Matrix(Matrix&& other) noexcept;
  Matrix& operator=(Matrix other) noexcept;
  std::size_t rows() const noexcept { return rows_; }
  std::size_t columns() const noexcept { return columns_; }
  const std::vector<double>& values() const noexcept { return values_; }
  double& operator()(std::size_t row, std::size_t column);
  double operator()(std::size_t row, std::size_t column) const;
private:
  std::size_t offset(std::size_t row, std::size_t column) const;
  std::size_t rows_ = 0, columns_ = 0;
  std::vector<double> values_;
};

struct StepSelection { std::string name; std::vector<std::int64_t> frames; };
class Selection {
public:
  Selection(std::vector<std::string> instances, std::vector<StepSelection> steps);
  const std::vector<std::string>& instances() const noexcept { return instances_; }
  const std::vector<StepSelection>& steps() const noexcept { return steps_; }
private:
  std::vector<std::string> instances_;
  std::vector<StepSelection> steps_;
};

struct StepInfo { std::string name; std::size_t frame_count; };
struct Element { Label label; std::vector<Label> connectivity; std::string type; };
struct InstanceMesh {
  std::string name;
  std::vector<Label> node_labels;
  Matrix coordinates;
  std::vector<Element> elements;
};
struct MeshData {
  Matrix points;
  std::vector<std::int64_t> connectivity, offsets, cell_types;
};
struct SectionPoint {
  int number;
  std::string description;
  bool operator==(const SectionPoint& other) const {
    return number == other.number && description == other.description;
  }
  bool operator!=(const SectionPoint& other) const { return !(*this == other); }
};
struct FieldLayout {
  std::string kind;
  std::vector<std::string> components;
  std::string position;
};
struct FieldInfo {
  std::string name;
  FieldLayout layout;
  std::vector<SectionPoint> sections;
  std::size_t max_integration_point = 1;
};
struct FieldBlock {
  std::string instance, position;
  std::vector<Label> labels;
  Matrix values;
  std::vector<std::int64_t> integration_points;
  std::optional<SectionPoint> section;
};
struct OrientationBlock { std::string instance; std::vector<Label> labels; Matrix quaternions; };
struct HistorySeries { std::string name; std::vector<double> timestamps, values; };
struct HistoryTable { std::vector<std::string> headers; Matrix values; };
struct FieldMetadata {
  std::string name, association, kind;
  std::vector<std::string> components;
  std::size_t width;
};
struct FieldArray { FieldMetadata metadata; Matrix values; };
struct FrameInfo { std::string step; std::size_t index; double time; };
struct Diagnostic { std::string step; std::size_t frame; std::string field, message; };
struct ConversionResult { std::size_t frames = 0; std::vector<Diagnostic> diagnostics; };
}
