#pragma once
#include "source.hpp"

namespace odb2vtk_core {
struct MemoryField { FieldInfo info; std::vector<FieldBlock> blocks; };
struct MemoryFrame { double time; std::vector<MemoryField> fields; std::vector<OrientationBlock> orientations; };
struct MemoryStep { std::string name; std::vector<MemoryFrame> frames; std::vector<HistorySeries> history; };
// Constructor copies/moves complete plain data. Queries return independent copies.
class InMemorySource final : public Source {
public:
  InMemorySource(std::vector<InstanceMesh> meshes, std::vector<MemoryStep> steps);
  bool closed() const noexcept override { return closed_; }
  void close() override { closed_ = true; }
  std::vector<std::string> instance_names() const override;
  std::vector<StepInfo> steps() const override;
  InstanceMesh mesh(const std::string&) const override;
  double frame_time(const std::string&,std::size_t) const override;
  std::vector<std::string> field_names(const std::string&,std::size_t) const override;
  FieldInfo describe_field(const std::string&,std::size_t,const std::string&,
      const std::vector<std::string>&) const override;
  void field_blocks(const std::string&,std::size_t,const std::string&,const std::string&,
      const std::string&,const std::optional<SectionPoint>&,const BlockVisitor&) const override;
  void orientation_blocks(const std::string&,std::size_t,const std::vector<std::string>&,
      const OrientationVisitor&) const override;
  std::vector<HistorySeries> history(const std::string&) const override;
private:
  void require_open() const;
  const InstanceMesh& find_mesh(const std::string&) const;
  const MemoryStep& step(const std::string&) const;
  const MemoryFrame& frame(const std::string&,std::size_t) const;
  const MemoryField& field(const std::string&,std::size_t,const std::string&) const;
  std::vector<InstanceMesh> meshes_;
  std::vector<MemoryStep> steps_;
  bool closed_ = false;
};
}
