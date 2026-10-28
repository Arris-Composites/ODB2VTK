#pragma once

#include "outputs.hpp"
#include <exception>

namespace odb2vtk_core {
struct FrameExport {
  FrameInfo frame;
  std::filesystem::path path;
};
struct ExportResult {
  std::vector<std::filesystem::path> paths;
  std::vector<FrameExport> frames;
  std::vector<Diagnostic> diagnostics;
};
class ExportFailure : public OutputError {
public:
  ExportFailure(std::string message, ExportResult result,
                std::exception_ptr cause);
  const ExportResult &result() const noexcept { return result_; }
  const std::exception_ptr &cause() const noexcept { return cause_; }

private:
  ExportResult result_;
  std::exception_ptr cause_;
};
struct ProgressEvent {
  std::string kind;
  std::filesystem::path path;
  std::size_t completed, total;
};
using Progress = std::function<void(const ProgressEvent &)>;

// Complete output operations over a caller-owned source. Source ownership and
// numerical conversion stay separate from serialization and publication.
class Exporter {
public:
  explicit Exporter(Source &source, Progress progress = {});
  ExportResult export_frames(const Selection &, const OutputOptions &) const;
  ExportResult export_header(const OutputOptions &) const;
  ExportResult export_history(const Selection &, const OutputOptions &) const;
  ExportResult export_collection(const Selection &,
                                 const OutputOptions &) const;
  // Preflight complete requests without geometry reads or output creation.
  std::vector<FrameExport> validate_frames(const Selection &,
                                           const OutputOptions &) const;
  void validate_history(const Selection &, const OutputOptions &) const;
  std::vector<FrameExport> validate_collection(const Selection &,
                                               const OutputOptions &) const;

private:
  void report(const std::string &, const std::filesystem::path &,
              std::size_t completed, std::size_t total) const;
  Source &source_;
  Progress progress_;
};
} // namespace odb2vtk_core
