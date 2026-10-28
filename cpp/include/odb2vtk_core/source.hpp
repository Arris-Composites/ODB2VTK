#pragma once
#include "models.hpp"
#include <functional>

namespace odb2vtk_core {
using BlockVisitor = std::function<void(FieldBlock)>;
using OrientationVisitor = std::function<void(OrientationBlock)>;

// Sources return owned records. Visitors are synchronous and must not be retained.
// A converter borrows its source; the caller controls source lifetime/closure.
class Source {
public:
  virtual ~Source() = default;
  virtual bool closed() const noexcept = 0;
  virtual void close() = 0;
  virtual std::vector<std::string> instance_names() const = 0;
  virtual std::vector<StepInfo> steps() const = 0;
  virtual InstanceMesh mesh(const std::string& instance) const = 0;
  virtual double frame_time(const std::string& step, std::size_t frame) const = 0;
  virtual std::vector<std::string> field_names(const std::string& step, std::size_t frame) const = 0;
  virtual FieldInfo describe_field(const std::string& step, std::size_t frame,
      const std::string& field, const std::vector<std::string>& instances) const = 0;
  virtual void field_blocks(const std::string& step, std::size_t frame,
      const std::string& field, const std::string& instance, const std::string& position,
      const std::optional<SectionPoint>& section, const BlockVisitor& visit) const = 0;
  virtual void orientation_blocks(const std::string& step, std::size_t frame,
      const std::vector<std::string>& instances, const OrientationVisitor& visit) const = 0;
  virtual std::vector<HistorySeries> history(const std::string& step) const = 0;
};
}
