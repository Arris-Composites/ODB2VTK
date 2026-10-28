#include "odb2vtk_core/models.hpp"
#include <limits>
#include <unordered_set>
#include <utility>

namespace odb2vtk_core {
std::size_t detail::product(std::size_t a, std::size_t b) {
  if (b && a > std::numeric_limits<std::size_t>::max() / b)
    throw std::overflow_error("Numerical array size overflow");
  return a * b;
}
std::size_t detail::sum(std::size_t a, std::size_t b) {
  if (a > std::numeric_limits<std::size_t>::max() - b)
    throw std::overflow_error("Mesh size overflow");
  return a + b;
}
Matrix::Matrix(std::size_t rows, std::size_t columns)
    : rows_(rows), columns_(columns),
      values_(detail::product(rows, columns), 0.) {}
Matrix::Matrix(std::size_t rows, std::size_t columns,
               std::vector<double> values)
    : rows_(rows), columns_(columns), values_(std::move(values)) {
  if (values_.size() != detail::product(rows, columns))
    throw SourceError("Matrix storage does not match its shape");
}
Matrix::Matrix(Matrix &&other) noexcept
    : rows_(std::exchange(other.rows_, 0)),
      columns_(std::exchange(other.columns_, 0)),
      values_(std::move(other.values_)) {
  other.values_.clear();
}
Matrix &Matrix::operator=(Matrix other) noexcept {
  std::swap(rows_, other.rows_);
  std::swap(columns_, other.columns_);
  values_.swap(other.values_);
  return *this;
}
std::size_t Matrix::offset(std::size_t row, std::size_t column) const {
  if (row >= rows_ || column >= columns_)
    throw std::out_of_range("Matrix index out of range");
  return row * columns_ + column;
}
double &Matrix::operator()(std::size_t row, std::size_t column) {
  return values_[offset(row, column)];
}
double Matrix::operator()(std::size_t row, std::size_t column) const {
  return values_[offset(row, column)];
}

Selection::Selection(std::vector<std::string> instances,
                     std::vector<StepSelection> steps)
    : instances_(std::move(instances)), steps_(std::move(steps)) {
  std::unordered_set<std::string> names;
  for (const auto &name : instances_)
    if (name.empty() || !names.insert(name).second)
      throw SelectionError("Invalid or duplicate instance name");
  if (steps_.empty())
    throw SelectionError("Select at least one step");
  names.clear();
  for (const auto &step : steps_) {
    if (step.name.empty() || !names.insert(step.name).second)
      throw SelectionError("Invalid or duplicate step name");
    std::unordered_set<std::int64_t> frames;
    for (auto frame : step.frames)
      if (frame < 0 || !frames.insert(frame).second)
        throw SelectionError("Invalid or duplicate frame index");
  }
}
} // namespace odb2vtk_core
