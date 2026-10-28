#pragma once
#include "source.hpp"

namespace odb2vtk_core {
// Sinks borrow frame/array inputs for the duration of each synchronous call.
class FrameSink {
public:
  virtual ~FrameSink() = default;
  virtual void begin_frame(const FrameInfo&, const MeshData&, const std::vector<FieldMetadata>&) = 0;
  virtual void field(const FieldArray&) = 0;
  virtual void end_frame() = 0;
};
class Converter {
public:
  explicit Converter(Source& source) : source_(source) {}
  ConversionResult convert(const Selection& selection, FrameSink& sink) const;
  HistoryTable history(const Selection& selection) const;
private:
  void validate(const Selection&, bool frames) const;
  Source& source_;
};
}
