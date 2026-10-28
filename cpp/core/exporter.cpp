#include "odb2vtk_core/exporter.hpp"
#include "atomic_file.hpp"
#include "profiling.hpp"
#include <memory>

namespace odb2vtk_core {
namespace {
std::vector<CollectionEntry>
collection_entries(const std::vector<FrameExport> &frames) {
  std::vector<CollectionEntry> entries;
  entries.reserve(frames.size());
  for (std::size_t i = 0; i < frames.size(); ++i)
    entries.push_back(
        {frames[i].frame.time, i, frames[i].path.filename().u8string()});
  return entries;
}
[[noreturn]] void failed(const char *operation, ExportResult result) {
  const auto cause = std::current_exception();
  std::string message = operation;
  try {
    std::rethrow_exception(cause);
  } catch (const std::exception &error) {
    message += std::string(": ") + error.what();
  } catch (...) {
    message += ": unknown failure";
  }
  throw ExportFailure(std::move(message), std::move(result), cause);
}
class FileSink final : public FrameSink {
public:
  FileSink(const OutputOptions &outputs,
           const std::vector<FrameExport> &expected,
           std::function<void(FrameExport)> completed)
      : outputs_(outputs), expected_(expected),
        completed_(std::move(completed)) {}
  void begin_frame(const FrameInfo &frame, const MeshData &mesh,
                   const std::vector<FieldMetadata> &metadata) override {
    if (file_ || next_ >= expected_.size())
      throw OutputError("Unexpected output frame");
    const auto &expected = expected_[next_];
    if (frame.step != expected.frame.step ||
        frame.index != expected.frame.index)
      throw OutputError("Output frame differs from validated request");
    pending_ = {frame, expected.path};
    file_ = std::make_unique<detail::AtomicFile>(pending_.path);
    writer_ = std::make_unique<VtuWriter>(file_->stream(), outputs_.format());
    writer_->begin_frame(frame, mesh, metadata);
  }
  void field(const FieldArray &field) override {
    if (!writer_)
      throw OutputError("No output frame in progress");
    writer_->field(field);
  }
  void end_frame() override {
    if (!writer_)
      throw OutputError("No output frame in progress");
    writer_->end_frame();
    writer_.reset();
    file_->publish();
    file_.reset();
    ++next_;
    completed_(std::move(pending_));
  }

private:
  const OutputOptions &outputs_;
  const std::vector<FrameExport> &expected_;
  std::function<void(FrameExport)> completed_;
  FrameExport pending_;
  std::size_t next_ = 0;
  // Declaration order ensures the writer releases its stream before file
  // cleanup.
  std::unique_ptr<detail::AtomicFile> file_;
  std::unique_ptr<VtuWriter> writer_;
};
} // namespace
ExportFailure::ExportFailure(std::string message, ExportResult result,
                             std::exception_ptr cause)
    : OutputError(std::move(message)), result_(std::move(result)),
      cause_(std::move(cause)) {}
Exporter::Exporter(Source &source, Progress progress)
    : source_(source), progress_(std::move(progress)) {}
void Exporter::report(const std::string &kind,
                      const std::filesystem::path &path, std::size_t completed,
                      std::size_t total) const {
  if (progress_)
    progress_({kind, path, completed, total});
}
std::vector<FrameExport>
Exporter::validate_frames(const Selection &selection,
                          const OutputOptions &outputs) const {
  detail::PhaseScope timing(detail::Phase::validation);
  Converter(source_).validate(selection, true);
  std::vector<FrameExport> frames;
  std::vector<std::filesystem::path> paths;
  for (const auto &step : selection.steps())
    for (auto index : step.frames) {
      const auto frame = static_cast<std::size_t>(index);
      const auto path = outputs.frame_path(step.name, frame);
      frames.push_back(
          {{step.name, frame, source_.frame_time(step.name, frame)}, path});
      paths.push_back(path);
    }
  if (outputs.write_pvd())
    paths.push_back(outputs.collection_path());
  validate_destinations(paths);
  return frames;
}
ExportResult Exporter::export_frames(const Selection &selection,
                                     const OutputOptions &outputs) const {
  const auto expected = validate_frames(selection, outputs);
  ExportResult result;
  result.frames.reserve(expected.size());
  result.paths.reserve(detail::sum(expected.size(), 1));
  try {
    FileSink sink(outputs, expected, [&](FrameExport frame) {
      auto path = frame.path;
      result.frames.push_back(std::move(frame));
      result.paths.push_back(std::move(path));
      report("frame_completed", result.paths.back(), result.frames.size(),
             expected.size());
    });
    result.diagnostics =
        Converter(source_).convert(selection, sink).diagnostics;
    if (outputs.write_pvd()) {
      detail::PhaseScope timing(detail::Phase::collection);
      const auto entries = collection_entries(result.frames);
      const auto path = outputs.collection_path();
      atomic_output(path,
                    [&](std::ostream &out) { write_collection(out, entries); });
      result.paths.push_back(path);
      report("collection_completed", path, result.frames.size(),
             expected.size());
    }
  } catch (...) {
    failed("Frame export failed", std::move(result));
  }
  return result;
}
ExportResult Exporter::export_header(const OutputOptions &outputs) const {
  if (source_.closed())
    throw SourceError("ODB source is closed");
  const auto path = outputs.header_path();
  validate_destinations({path});
  ExportResult result;
  try {
    const auto instances = source_.instance_names();
    const auto steps = source_.steps();
    atomic_output(
        path, [&](std::ostream &out) { write_header(out, instances, steps); });
    result.paths.push_back(path);
    report("header_completed", path, 1, 1);
  } catch (...) {
    failed("Header export failed", std::move(result));
  }
  return result;
}
ExportResult Exporter::export_history(const Selection &selection,
                                      const OutputOptions &outputs) const {
  detail::PhaseScope timing(detail::Phase::history);
  validate_history(selection, outputs);
  const auto path = outputs.history_path();
  ExportResult result;
  try {
    const auto table = Converter(source_).history(selection);
    atomic_output(path, [&](std::ostream &out) { write_history(out, table); });
    result.paths.push_back(path);
    report("history_completed", path, 1, 1);
  } catch (...) {
    failed("History export failed", std::move(result));
  }
  return result;
}
void Exporter::validate_history(const Selection &selection,
                                const OutputOptions &outputs) const {
  detail::PhaseScope timing(detail::Phase::validation);
  Converter(source_).validate(selection, false);
  validate_destinations({outputs.history_path()});
}
std::vector<FrameExport>
Exporter::validate_collection(const Selection &selection,
                              const OutputOptions &outputs) const {
  detail::PhaseScope timing(detail::Phase::validation);
  const auto frames = validate_frames(selection, outputs);
  const auto path = outputs.collection_path();
  validate_destinations({path});
  for (const auto &frame : frames) {
    std::error_code error;
    if (!std::filesystem::is_regular_file(frame.path, error) || error)
      throw OutputError("Cannot write collection; VTU file is missing: " +
                        frame.path.u8string());
  }
  return frames;
}
ExportResult Exporter::export_collection(const Selection &selection,
                                         const OutputOptions &outputs) const {
  detail::PhaseScope timing(detail::Phase::collection);
  const auto frames = validate_collection(selection, outputs);
  const auto path = outputs.collection_path();
  ExportResult result;
  try {
    const auto entries = collection_entries(frames);
    atomic_output(path,
                  [&](std::ostream &out) { write_collection(out, entries); });
    result.paths.push_back(path);
    report("collection_completed", path, frames.size(), frames.size());
  } catch (...) {
    failed("Collection export failed", std::move(result));
  }
  return result;
}
} // namespace odb2vtk_core
