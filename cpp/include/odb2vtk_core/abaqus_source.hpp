#pragma once
#include "source.hpp"
#include <memory>

namespace odb2vtk_core {
// SDK types and global API lifetime are private to the implementation.
class AbaqusSource final : public Source {
public:
  explicit AbaqusSource(const std::string &path);
  ~AbaqusSource() noexcept override;
  AbaqusSource(const AbaqusSource &) = delete;
  AbaqusSource &operator=(const AbaqusSource &) = delete;
  bool closed() const noexcept override;
  void close() override;
  std::vector<std::string> instance_names() const override;
  std::vector<StepInfo> steps() const override;
  InstanceMesh mesh(const std::string &) const override;
  double frame_time(const std::string &, std::size_t) const override;
  std::vector<std::string> field_names(const std::string &,
                                       std::size_t) const override;
  FieldInfo describe_field(const std::string &, std::size_t,
                           const std::string &,
                           const std::vector<std::string> &) const override;
  void field_blocks(const std::string &, std::size_t, const std::string &,
                    const std::string &, const std::string &,
                    const std::optional<SectionPoint> &,
                    const BlockVisitor &) const override;
  void orientation_blocks(const std::string &, std::size_t,
                          const std::vector<std::string> &,
                          const OrientationVisitor &) const override;
  std::vector<HistorySeries> history(const std::string &) const override;

private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
} // namespace odb2vtk_core
