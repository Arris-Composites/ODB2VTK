#pragma once

#include "converter.hpp"
#include <iosfwd>
#include <memory>

namespace odb2vtk_core {
enum class VtuFormat { ascii, binary };
class OutputError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

struct CollectionEntry {
  double timestep;
  std::size_t part;
  std::string filename;
};

// Borrows its stream. Consumes fields synchronously, retaining only metadata
// and the mesh until end_frame(). The caller owns publication and stream
// lifetime. Both formats require fields in the declared point-before-cell
// order.
class VtuWriter final : public FrameSink {
public:
  VtuWriter(std::ostream &, VtuFormat = VtuFormat::ascii);
  ~VtuWriter();
  VtuWriter(const VtuWriter &) = delete;
  VtuWriter &operator=(const VtuWriter &) = delete;
  void begin_frame(const FrameInfo &, const MeshData &,
                   const std::vector<FieldMetadata> &) override;
  void field(const FieldArray &) override;
  void end_frame() override;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

void write_header(std::ostream &, const std::vector<std::string> &instances,
                  const std::vector<StepInfo> &steps);
void write_history(std::ostream &, const HistoryTable &);
void write_collection(std::ostream &, const std::vector<CollectionEntry> &);
} // namespace odb2vtk_core
