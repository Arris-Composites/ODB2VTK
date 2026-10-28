#include "odb2vtk_core/converter.hpp"
#include "odb2vtk_core/conversion.hpp"
#include <algorithm>
#include <unordered_map>
#include <unordered_set>

namespace odb2vtk_core {
namespace {
struct Plan {
  FieldMetadata metadata;
  std::string source, position;
  std::optional<SectionPoint> section;
};
std::vector<Plan> plans(Source& source, const FrameInfo& frame,
    const std::vector<std::string>& instances, std::vector<Diagnostic>& diagnostics) {
  std::vector<Plan> result;
  const auto names = source.field_names(frame.step, frame.index);
  for (const auto& name : names) {
    const auto info = source.describe_field(frame.step, frame.index, name, instances);
    if (info.name != name) throw SourceError("Field metadata identity mismatch");
    const auto& layout = info.layout;
    if (layout.position != "NODAL" && layout.position != "INTEGRATION_POINT") {
      diagnostics.push_back({frame.step, frame.index, name, "Unsupported field position: " + layout.position});
      continue;
    }
    if (layout.components.empty() || !info.max_integration_point)
      throw SourceError("Invalid field component or integration-point count");
    auto add = [&](const std::string& output_name, const std::string& association,
                   const std::string& position, std::size_t points) {
      auto components = layout.components;
      components.reserve(detail::product(components.size(), points));
      for (std::size_t i = 1; i < points; ++i)
        components.insert(components.end(), layout.components.begin(), layout.components.end());
      auto append = [&](std::optional<SectionPoint> section) {
        result.push_back({{output_name + (section ? section->description : ""), association,
                           layout.kind, components, components.size()}, name, position, section});
      };
      if (info.sections.empty()) append(std::nullopt);
      else for (const auto& section : info.sections) append(section);
    };
    if (layout.position == "NODAL") add(name, "PointData", "NODAL", 1);
    else {
      add(name + "_Centroid", "CellData", "CENTROID", 1);
      add(name + "_IntegrationPoints", "CellData", "INTEGRATION_POINT", info.max_integration_point);
    }
  }
  if (std::find(names.begin(), names.end(), "S") != names.end())
    result.push_back({{"Material_Orientation", "CellData", "Vectors", {}, 3}, "", "", std::nullopt});
  std::stable_partition(result.begin(), result.end(), [](const Plan& p) { return p.metadata.association == "PointData"; });
  return result;
}
FieldArray read(Source& source, const Plan& plan, const FrameInfo& frame,
    const Selection& selection, const PreparedMesh& prepared) {
  if (plan.source.empty()) {
    Matrix quaternions(prepared.geometry.offsets.size(), 4);
    source.orientation_blocks(frame.step, frame.index, selection.instances(), [&](OrientationBlock block) {
      if (block.labels.size() != block.quaternions.rows() || !block.quaternions.columns() || block.quaternions.columns() > 4)
        throw SourceError("Invalid orientation block shape");
      const auto found = prepared.elements.find(block.instance);
      if (found == prepared.elements.end()) throw SourceError("Unexpected orientation instance");
      const auto& lookup = found->second;
      auto rows = lookup.rows(block.labels);
      for (auto row : rows) if (row >= quaternions.rows()) throw SourceError("Orientation row out of range");
      for (std::size_t i = 0; i < rows.size(); ++i)
        for (std::size_t c = 0; c < block.quaternions.columns(); ++c)
          quaternions(rows[i],c)=block.quaternions(i,c);
    });
    return {plan.metadata, quaternion_directions(quaternions)};
  }
  const bool point = plan.metadata.association == "PointData";
  Matrix values(point ? prepared.geometry.points.rows() : prepared.geometry.offsets.size(), plan.metadata.width);
  for (const auto& instance : selection.instances()) {
    source.field_blocks(frame.step, frame.index, plan.source, instance, plan.position, plan.section,
      [&](FieldBlock block) {
        if (block.instance != instance || block.position != plan.position || block.section != plan.section)
          throw SourceError("Field block identity/position/section differs from request");
        if (point) place_points(block, prepared.nodes.at(instance), values);
        else place_cells(block, prepared.elements.at(instance), values);
      });
  }
  return {plan.metadata, std::move(values)};
}
}
void Converter::validate(const Selection& selection, bool frames) const {
  if (source_.closed()) throw SourceError("ODB source is closed");
  if (frames && selection.instances().empty()) throw SelectionError("Select at least one instance");
  const auto names = selection.instances().empty() ? std::vector<std::string>{} : source_.instance_names();
  for (const auto& name : selection.instances())
    if (std::find(names.begin(), names.end(), name) == names.end()) throw SelectionError("Instance not found: " + name);
  std::unordered_map<std::string,std::size_t> steps;
  for (const auto& step : source_.steps()) steps.emplace(step.name,step.frame_count);
  for (const auto& step : selection.steps()) {
    const auto found = steps.find(step.name);
    if (found == steps.end()) throw SelectionError("Step not found: " + step.name);
    if (frames && step.frames.empty()) throw SelectionError("Select at least one frame for " + step.name);
    for (auto frame : step.frames)
      if (static_cast<std::uint64_t>(frame) >= found->second) throw SelectionError("Frame out of range for " + step.name);
  }
}
ConversionResult Converter::convert(const Selection& selection, FrameSink& sink) const {
  validate(selection,true);
  std::vector<InstanceMesh> snapshots;
  for (const auto& name : selection.instances()) {
    auto mesh = source_.mesh(name);
    if (mesh.name != name) throw SourceError("Mesh instance identity differs from request");
    snapshots.push_back(std::move(mesh));
  }
  const auto prepared = prepare_mesh(snapshots);
  snapshots.clear(); // Geometry and maps own their storage, independently of source snapshots.
  ConversionResult result;
  for (const auto& step : selection.steps()) for (auto index : step.frames) {
    const FrameInfo frame{step.name, static_cast<std::size_t>(index), source_.frame_time(step.name,static_cast<std::size_t>(index))};
    const auto fields = plans(source_,frame,selection.instances(),result.diagnostics);
    std::vector<FieldMetadata> metadata;
    for (const auto& plan : fields) metadata.push_back(plan.metadata);
    sink.begin_frame(frame,prepared.geometry,metadata);
    for (const auto& plan : fields) sink.field(read(source_,plan,frame,selection,prepared));
    sink.end_frame();
    ++result.frames;
  }
  return result;
}
HistoryTable Converter::history(const Selection& selection) const {
  validate(selection,false);
  std::vector<HistorySeries> series;
  for (const auto& step : selection.steps()) {
    auto items = source_.history(step.name);
    for (auto& item : items) series.push_back(std::move(item));
  }
  return assemble_history(series);
}
}
