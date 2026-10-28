#pragma once

#include "exporter.hpp"
#include <iosfwd>
#include <memory>
#include <optional>

namespace odb2vtk_core {
class ArgumentError : public std::invalid_argument {
public:
  using std::invalid_argument::invalid_argument;
};
enum class ExportMode { header, frames, collection };
struct CliRequest {
  std::filesystem::path odb_file;
  ExportMode mode;
  std::optional<Selection> selection;
  OutputOptions outputs;
  bool write_history;
};
using SourceFactory =
    std::function<std::unique_ptr<Source>(const std::filesystem::path &)>;

// nullopt means help was requested. Parsing validates the input file and builds
// a complete request without constructing a Source or initializing the SDK.
std::optional<CliRequest>
parse_request(const std::vector<std::string> &arguments);
void print_help(std::ostream &);

// Owns the factory-created source. All modes close explicitly before returning;
// on failure cleanup preserves the originating error and completed receipts.
ExportResult execute_request(const CliRequest &, const SourceFactory &,
                             Progress = {});
int cli_main(const std::vector<std::string> &arguments, const SourceFactory &,
             std::ostream &output, std::ostream &errors);
} // namespace odb2vtk_core
