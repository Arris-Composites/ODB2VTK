#include "odb2vtk_core/in_memory_source.hpp"
#include <algorithm>
#include <unordered_set>
#include <utility>

namespace odb2vtk_core {
InMemorySource::InMemorySource(std::vector<InstanceMesh> meshes,
                               std::vector<MemoryStep> steps)
    : meshes_(std::move(meshes)), steps_(std::move(steps)) {
  std::unordered_set<std::string> names;
  for (const auto &mesh : meshes_)
    if (mesh.name.empty() || !names.insert(mesh.name).second)
      throw SourceError("Invalid or duplicate instance");
  names.clear();
  for (const auto &step : steps_) {
    if (step.name.empty() || !names.insert(step.name).second)
      throw SourceError("Invalid or duplicate step");
    for (const auto &frame : step.frames) {
      std::unordered_set<std::string> fields;
      for (const auto &field : frame.fields)
        if (field.info.name.empty() || !fields.insert(field.info.name).second)
          throw SourceError("Invalid or duplicate field name");
    }
  }
}
void InMemorySource::require_open() const {
  if (closed_)
    throw SourceError("ODB source is closed");
}
const MemoryStep &InMemorySource::step(const std::string &name) const {
  require_open();
  for (const auto &value : steps_)
    if (value.name == name)
      return value;
  throw SourceError("Step not found: " + name);
}
const MemoryFrame &InMemorySource::frame(const std::string &name,
                                         std::size_t index) const {
  const auto &frames = step(name).frames;
  if (index >= frames.size())
    throw SourceError("Frame out of range");
  return frames[index];
}
const MemoryField &InMemorySource::field(const std::string &name,
                                         std::size_t index,
                                         const std::string &key) const {
  for (const auto &value : frame(name, index).fields)
    if (value.info.name == key)
      return value;
  throw SourceError("Field not found: " + key);
}
std::vector<std::string> InMemorySource::instance_names() const {
  require_open();
  std::vector<std::string> result;
  for (const auto &mesh : meshes_)
    result.push_back(mesh.name);
  return result;
}
std::vector<StepInfo> InMemorySource::steps() const {
  require_open();
  std::vector<StepInfo> result;
  for (const auto &step : steps_)
    result.push_back({step.name, step.frames.size()});
  return result;
}
const InstanceMesh &InMemorySource::find_mesh(const std::string &name) const {
  require_open();
  for (const auto &value : meshes_)
    if (value.name == name)
      return value;
  throw SourceError("Instance not found: " + name);
}
InstanceMesh InMemorySource::mesh(const std::string &name) const {
  return find_mesh(name);
}
double InMemorySource::frame_time(const std::string &name,
                                  std::size_t index) const {
  return frame(name, index).time;
}
std::vector<std::string> InMemorySource::field_names(const std::string &name,
                                                     std::size_t index) const {
  std::vector<std::string> result;
  for (const auto &value : frame(name, index).fields)
    result.push_back(value.info.name);
  return result;
}
FieldInfo InMemorySource::describe_field(
    const std::string &name, std::size_t index, const std::string &key,
    const std::vector<std::string> &instances) const {
  const auto &value = field(name, index, key);
  auto result = value.info;
  result.sections.clear();
  result.max_integration_point = 1;
  for (const auto &instance : instances) {
    find_mesh(instance);
    for (const auto &block : value.blocks) {
      if (block.instance != instance ||
          block.position != result.layout.position)
        continue;
      if (block.section) {
        auto found =
            std::find_if(result.sections.begin(), result.sections.end(),
                         [&](const SectionPoint &p) {
                           return p.description == block.section->description;
                         });
        if (found == result.sections.end())
          result.sections.push_back(*block.section);
        else
          *found = *block.section;
      }
      for (auto point : block.integration_points)
        if (point > 0)
          result.max_integration_point = std::max(
              result.max_integration_point, static_cast<std::size_t>(point));
    }
  }
  return result;
}
void InMemorySource::field_blocks(const std::string &step, std::size_t index,
                                  const std::string &name,
                                  const std::string &instance,
                                  const std::string &position,
                                  const std::optional<SectionPoint> &section,
                                  const BlockVisitor &visit) const {
  find_mesh(instance);
  if (position != "NODAL" && position != "CENTROID" &&
      position != "INTEGRATION_POINT")
    throw SourceError("Unsupported requested position: " + position);
  for (const auto &block : field(step, index, name).blocks) {
    require_open();
    if (block.instance == instance && block.position == position &&
        (!section || block.section == section))
      visit(block);
  }
}
void InMemorySource::orientation_blocks(
    const std::string &name, std::size_t index,
    const std::vector<std::string> &instances,
    const OrientationVisitor &visit) const {
  for (const auto &instance : instances)
    find_mesh(instance);
  for (const auto &block : frame(name, index).orientations) {
    require_open();
    if (std::find(instances.begin(), instances.end(), block.instance) !=
        instances.end())
      visit(block);
  }
}
std::vector<HistorySeries>
InMemorySource::history(const std::string &name) const {
  return step(name).history;
}
} // namespace odb2vtk_core
