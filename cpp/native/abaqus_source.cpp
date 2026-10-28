#include "odb2vtk_core/abaqus_source.hpp"
#include "../core/profiling.hpp"
#include <algorithm>
#include <atomic>
#include <filesystem>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <utility>
#include <odb_API.h>

namespace odb2vtk_core {
namespace {
template<class F> auto sdk(F&& function) -> decltype(function()) {
  try { return function(); }
  catch (odb_BaseException& error) { throw SourceError(error.UserReport().CStr()); }
}
struct RuntimeState { std::mutex mutex; std::size_t users = 0; };
RuntimeState& state() { static RuntimeState value; return value; }
class RuntimeLease {
public:
  RuntimeLease() {
    auto& value = state(); std::lock_guard<std::mutex> lock(value.mutex);
    if (!value.users) sdk([] { odb_initializeAPI(); });
    ++value.users;
  }
  ~RuntimeLease() noexcept { try { close(); } catch (...) {} }
  RuntimeLease(const RuntimeLease&) = delete;
  RuntimeLease& operator=(const RuntimeLease&) = delete;
  void close() {
    auto& value = state(); std::lock_guard<std::mutex> lock(value.mutex);
    if (!active_) return;
    active_ = false;
    if (--value.users == 0) sdk([] { odb_finalizeAPI(); });
  }
private:
  bool active_ = true;
};
std::size_t count(int size) {
  if (size < 0) throw SourceError("Negative native array length");
  return static_cast<std::size_t>(size);
}
std::optional<SectionPoint> section(const odb_SectionPoint& value) {
  if (value.number() < 0) return std::nullopt;
  return SectionPoint{value.number(),value.description().CStr()};
}
std::string position_name(odb_Enum::odb_ResultPositionEnum position) {
  if (position == odb_Enum::NODAL) return "NODAL";
  if (position == odb_Enum::CENTROID) return "CENTROID";
  if (position == odb_Enum::INTEGRATION_POINT) return "INTEGRATION_POINT";
  if (position == odb_Enum::ELEMENT_NODAL) return "ELEMENT_NODAL";
  if (position == odb_Enum::ELEMENT_FACE) return "ELEMENT_FACE";
  return "unsupported(" + std::to_string(static_cast<int>(position)) + ")";
}
odb_Enum::odb_ResultPositionEnum native_position(const std::string& position) {
  if (position == "NODAL") return odb_Enum::NODAL;
  if (position == "CENTROID") return odb_Enum::CENTROID;
  if (position == "INTEGRATION_POINT") return odb_Enum::INTEGRATION_POINT;
  throw SourceError("Unsupported requested position: " + position);
}
Matrix copy_values(const float* single,const double* dual,bool is_double,
                   std::size_t rows,std::size_t columns) {
  if (!columns) throw SourceError("Native block has no components");
  if (rows && (is_double ? !dual : !single)) throw SourceError("Missing native numerical data");
  Matrix values(rows,columns);
  for (std::size_t row = 0; row < rows; ++row)
    for (std::size_t c = 0; c < columns; ++c)
      values(row,c)=is_double ? dual[row*columns+c] : static_cast<double>(single[row*columns+c]);
  return values;
}
std::vector<Label> copy_labels(const int* labels,std::size_t rows) {
  if (rows && !labels) throw SourceError("Missing native labels");
  std::vector<Label> result; result.reserve(rows);
  for (std::size_t i = 0; i < rows; ++i) result.push_back(labels[i]);
  return result;
}

// The SDK's distinct handles for the same physical file are not independent:
// closing one can invalidate its peers. Share one native owner, not just API state.
struct DatabaseState {
  std::shared_ptr<RuntimeLease> runtime=std::make_shared<RuntimeLease>();
  std::filesystem::path path;
  odb_Odb* db=nullptr;
  explicit DatabaseState(const std::filesystem::path& file) : path(file) {
    static std::atomic<std::uint64_t> next{1};
    const auto name="odb2vtk_source_"+std::to_string(next.fetch_add(1));
    const auto filename=path.string();
    db=sdk([&] { return &openOdb(odb_String(name.c_str()),odb_String(filename.c_str()),true); });
  }
  ~DatabaseState() noexcept { try { close(); } catch (...) {} }
  void close() {
    if (!db) return;
    auto* value=db;db=nullptr;
    try { sdk([&] { value->close(); }); }
    catch (...) { runtime.reset();throw; }
    runtime->close();runtime.reset();
  }
};
std::shared_ptr<DatabaseState> acquire_database(const std::string& path) {
  static std::mutex mutex;
  static std::vector<std::weak_ptr<DatabaseState>> owners;
  const auto file=std::filesystem::weakly_canonical(std::filesystem::absolute(path));
  std::lock_guard<std::mutex> lock(mutex);
  for (auto it=owners.begin(); it!=owners.end();) {
    auto owner=it->lock();
    if (!owner) { it=owners.erase(it);continue; }
    std::error_code error;
    if (owner->db && (owner->path==file || std::filesystem::equivalent(owner->path,file,error))) return owner;
    ++it;
  }
  auto owner=std::make_shared<DatabaseState>(file);owners.push_back(owner);return owner;
}
}

struct AbaqusSource::Impl {
  std::shared_ptr<DatabaseState> database;
  odb_Odb* db = nullptr;
  std::optional<odb_Frame> current_frame;
  std::string current_step;
  std::size_t current_index = 0;
  std::map<std::string,odb_FieldOutput> fields;

  explicit Impl(const std::string& path) {
    database=acquire_database(path);db=database->db;
  }
  void require_open() const { if (!db) throw SourceError("ODB source is closed"); }
  void clear_frame() { fields.clear(); current_frame.reset(); current_step.clear(); }
  odb_Frame& frame(const std::string& step,std::size_t index) {
    require_open();
    if (!current_frame || current_step != step || current_index != index) {
      clear_frame();
      const auto& frames = db->steps().constGet(step.c_str()).frames();
      if (index >= count(frames.size())) throw SourceError("Frame out of range");
      current_frame.emplace(frames[static_cast<int>(index)]);
      current_step=step; current_index=index;
    }
    return *current_frame;
  }
  odb_FieldOutput& field(const std::string& step,std::size_t index,const std::string& name) {
    auto& native = frame(step,index);
    auto found = fields.find(name);
    if (found == fields.end())
      found = fields.emplace(name,native.fieldOutputs().constGet(name.c_str())).first;
    return found->second;
  }
  odb_SectionPoint native_section(const odb_FieldOutput& field,const SectionPoint& point) {
    const auto& blocks = field.bulkDataBlocks();
    for (int i = 0; i < blocks.size(); ++i) {
      const auto candidate = blocks[i].sectionPoint();
      if (candidate.number() == point.number && point.description == candidate.description().CStr()) return candidate;
    }
    throw SourceError("Section point not found: " + point.description);
  }
};

AbaqusSource::AbaqusSource(const std::string& path) {
  detail::PhaseScope timing(detail::Phase::odb_open);
  if (path.empty() || path.find('\0') != std::string::npos) throw SourceError("Invalid ODB path");
  impl_ = std::make_unique<Impl>(path);
}
AbaqusSource::~AbaqusSource() noexcept { try { close(); } catch (...) {} }
bool AbaqusSource::closed() const noexcept { return !impl_ || !impl_->db; }
void AbaqusSource::close() {
  detail::PhaseScope timing(detail::Phase::odb_close);
  if (closed()) return;
  impl_->clear_frame();
  impl_->db=nullptr;
  auto database=std::move(impl_->database);
  if (database.use_count()==1) database->close();
}
std::vector<std::string> AbaqusSource::instance_names() const {
  impl_->require_open(); auto lifetime=impl_->database;
  return sdk([&] {
    std::vector<std::string> result;
    odb_InstanceRepositoryIT it(impl_->db->rootAssembly().instances());
    for (it.first(); !it.isDone(); it.next()) result.emplace_back(it.currentKey().CStr());
    return result;
  });
}
std::vector<StepInfo> AbaqusSource::steps() const {
  impl_->require_open(); auto lifetime=impl_->database;
  return sdk([&] {
    std::vector<StepInfo> result;
    odb_StepRepositoryIT it(impl_->db->steps());
    for (it.first(); !it.isDone(); it.next()) result.push_back({it.currentKey().CStr(),count(it.currentValue().frames().size())});
    return result;
  });
}
InstanceMesh AbaqusSource::mesh(const std::string& name) const {
  impl_->require_open(); auto lifetime=impl_->database;
  return sdk([&] {
    const auto instance=impl_->db->rootAssembly().instances().constGet(name.c_str());
    const auto nodes=instance.nodes();
    InstanceMesh result{name,{},Matrix(count(nodes.size()),3),{}};
    result.node_labels.reserve(count(nodes.size()));
    for (int i = 0; i < nodes.size(); ++i) {
      const auto node=nodes[i]; result.node_labels.push_back(node.label());
      const auto* xyz=node.coordinates();
      for (std::size_t c = 0; c < 3; ++c) result.coordinates(static_cast<std::size_t>(i),c)=xyz[c];
    }
    const auto elements=instance.elements(); result.elements.reserve(count(elements.size()));
    for (int i = 0; i < elements.size(); ++i) {
      const auto element=elements[i]; int size=0; const auto* labels=element.connectivity(size);
      result.elements.push_back({element.label(),copy_labels(labels,count(size)),element.type().CStr()});
    }
    return result;
  });
}
double AbaqusSource::frame_time(const std::string& step,std::size_t frame) const {
  impl_->require_open(); auto lifetime=impl_->database;
  return sdk([&] { return impl_->frame(step,frame).frameValue(); });
}
std::vector<std::string> AbaqusSource::field_names(const std::string& step,std::size_t frame) const {
  impl_->require_open(); auto lifetime=impl_->database;
  return sdk([&] {
    std::vector<std::string> result;
    odb_FieldOutputRepositoryIT it(impl_->frame(step,frame).fieldOutputs());
    for (it.first(); !it.isDone(); it.next()) result.emplace_back(it.currentKey().CStr());
    return result;
  });
}
FieldInfo AbaqusSource::describe_field(const std::string& step,std::size_t frame,const std::string& name,
    const std::vector<std::string>& instances) const {
  impl_->require_open(); auto lifetime=impl_->database;
  return sdk([&] {
    const auto field=impl_->field(step,frame,name);
    if (!field.locations().size()) throw SourceError("Field has no locations: " + name);
    const auto position=field.locations()[0].position();
    FieldInfo result{name,{field.type()==odb_Enum::SCALAR ? "Scalars" : field.type()==odb_Enum::VECTOR ? "Vectors" : "Tensors",{},position_name(position)},{},1};
    const auto components=field.componentLabels();
    for (int i = 0; i < components.size(); ++i) result.layout.components.emplace_back(components[i].CStr());
    if (field.type()==odb_Enum::SCALAR && result.layout.components.empty()) result.layout.components.push_back("0");
    for (const auto& instance : instances) {
      const auto subset=field.getSubset(impl_->db->rootAssembly().instances().constGet(instance.c_str())).getSubset(position,true);
      const auto& blocks=subset.bulkDataBlocks();
      for (int i = 0; i < blocks.size(); ++i) {
        const auto& block=blocks[i];
        const auto point=section(block.sectionPoint());
        if (point) {
          auto found=std::find_if(result.sections.begin(),result.sections.end(),[&](const SectionPoint& p) { return p.description==point->description; });
          if (found==result.sections.end()) result.sections.push_back(*point); else *found=*point;
        }
        if (position==odb_Enum::INTEGRATION_POINT) {
          const auto* points=block.integrationPoints();
          if (block.length() && !points) throw SourceError("Missing integration-point identifiers");
          for (int row = 0; row < block.length(); ++row)
            if (points[row]>0) result.max_integration_point=std::max(result.max_integration_point,static_cast<std::size_t>(points[row]));
        }
      }
    }
    return result;
  });
}
void AbaqusSource::field_blocks(const std::string& step,std::size_t frame,const std::string& name,
    const std::string& instance,const std::string& position,const std::optional<SectionPoint>& point,
    const BlockVisitor& visit) const {
  detail::PhaseScope timing(detail::Phase::field_read);
  impl_->require_open(); auto lifetime=impl_->database;
  sdk([&] {
    auto field=impl_->field(step,frame,name);
    if (point) field=field.getSubset(impl_->native_section(field,*point));
    const auto subset=field.getSubset(impl_->db->rootAssembly().instances().constGet(instance.c_str())).getSubset(native_position(position),true);
    const auto& blocks=subset.bulkDataBlocks();
    const int size=blocks.size();
    for (int i = 0; i < size; ++i) {
      impl_->require_open();
      const auto& block=blocks[i]; const auto rows=count(block.length());
      const bool dual=block.precision()==odb_Enum::DOUBLE_PRECISION;
      FieldBlock result{instance,position_name(block.position()),
        copy_labels(position=="NODAL" ? block.nodeLabels() : block.elementLabels(),rows),
        copy_values(dual ? nullptr : block.data(),dual ? block.dataDouble() : nullptr,dual,rows,count(block.width())),{},section(block.sectionPoint())};
      if (position=="INTEGRATION_POINT") {
        const auto* points=block.integrationPoints();
        if (rows && !points) throw SourceError("Missing integration-point identifiers");
        for (std::size_t row=0; row<rows; ++row) result.integration_points.push_back(points[row]);
      }
      visit(std::move(result));
    }
  });
}
void AbaqusSource::orientation_blocks(const std::string& step,std::size_t frame,
    const std::vector<std::string>& instances,const OrientationVisitor& visit) const {
  detail::PhaseScope timing(detail::Phase::field_read);
  impl_->require_open(); auto lifetime=impl_->database;
  sdk([&] {
    const auto names=field_names(step,frame);
    if (std::find(names.begin(),names.end(),"S")==names.end()) return;
    const auto field=impl_->field(step,frame,"S");
    std::optional<odb_SectionPoint> first_section;
    if (!instances.empty()) {
      const auto subset=field.getSubset(impl_->db->rootAssembly().instances().constGet(instances[0].c_str())).getSubset(odb_Enum::CENTROID,true);
      if (subset.bulkDataBlocks().size() && section(subset.bulkDataBlocks()[0].sectionPoint()))
        first_section.emplace(subset.bulkDataBlocks()[0].sectionPoint());
    }
    for (const auto& instance : instances) {
      impl_->require_open();
      auto subset=field.getSubset(impl_->db->rootAssembly().instances().constGet(instance.c_str())).getSubset(odb_Enum::CENTROID,true);
      if (first_section) subset=subset.getSubset(*first_section);
      const auto& blocks=subset.bulkDataBlocks(); const int size=blocks.size();
      for (int i=0; i<size; ++i) {
        impl_->require_open();
        const auto& block=blocks[i];
        const bool dual=block.precision()==odb_Enum::DOUBLE_PRECISION;
        const auto* single=dual ? nullptr : block.localCoordSystem();
        const auto* doubles=dual ? block.localCoordSystemDouble() : nullptr;
        if (!single && !doubles) continue;
        const auto width=count(block.orientationWidth()), rows=count(block.length());
        if (!width || width>4) throw SourceError("Invalid native quaternion width");
        visit({instance,copy_labels(block.elementLabels(),rows),copy_values(single,doubles,dual,rows,width)});
      }
    }
  });
}
std::vector<HistorySeries> AbaqusSource::history(const std::string& step) const {
  impl_->require_open(); auto lifetime=impl_->database;
  return sdk([&] {
    std::vector<HistorySeries> result;
    odb_HistoryRegionRepositoryIT regions(impl_->db->steps().constGet(step.c_str()).historyRegions());
    for (regions.first(); !regions.isDone(); regions.next()) {
      odb_HistoryOutputRepositoryIT outputs(regions.currentValue().historyOutputs());
      for (outputs.first(); !outputs.isDone(); outputs.next()) {
        HistorySeries series{step+"_"+regions.currentKey().CStr()+"_"+outputs.currentKey().CStr(),{}, {}};
        const auto data=outputs.currentValue().data();
        for (int i=0; i<data.size(); ++i) {
          const auto row=data[i];
          if (row.size()!=2) throw SourceError("Malformed native history row");
          series.timestamps.push_back(row[0]); series.values.push_back(row[1]);
        }
        result.push_back(std::move(series));
      }
    }
    return result;
  });
}
}
