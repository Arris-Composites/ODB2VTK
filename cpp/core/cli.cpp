#include "odb2vtk_core/cli.hpp"
#include <charconv>
#include <iterator>
#include <ostream>
#include <unordered_map>

namespace odb2vtk_core {
namespace {
bool option(const std::string& text) { return !text.empty() && text.front() == '-'; }
bool boolean(const std::string& text, const std::string& flag) {
  if (text != "0" && text != "1") throw ArgumentError(flag + " must be 0 or 1");
  return text == "1";
}
Selection selection(const std::vector<std::string>& instances, const std::vector<std::string>& tokens) {
  if (instances.empty()) throw ArgumentError("--instance is required when --header is 0");
  if (tokens.empty()) throw ArgumentError("--step is required when --header is 0");
  std::vector<StepSelection> steps;
  for (const auto& token : tokens) {
    const auto colon = token.rfind(':');
    if (colon == std::string::npos || !colon || colon + 1 == token.size())
      throw ArgumentError("Invalid --step; use 'step_name:0,1,2': " + token);
    StepSelection step{token.substr(0, colon), {}};
    std::size_t start = colon + 1;
    while (start <= token.size()) {
      const auto comma = token.find(',', start);
      const auto end = comma == std::string::npos ? token.size() : comma;
      if (start == end) throw ArgumentError("Empty frame in --step: " + token);
      for (auto i = start; i < end; ++i)
        if (token[i] < '0' || token[i] > '9') throw ArgumentError("Frame lists require nonnegative integers: " + token);
      std::int64_t frame = 0;
      const auto parsed = std::from_chars(token.data()+start, token.data()+end, frame);
      if (parsed.ec != std::errc{} || parsed.ptr != token.data()+end)
        throw ArgumentError("Frame index is too large: " + token);
      step.frames.push_back(frame);
      if (comma == std::string::npos) break;
      start = comma + 1;
    }
    steps.push_back(std::move(step));
  }
  return Selection(instances, std::move(steps));
}
void append(ExportResult& destination, ExportResult source) {
  auto move = [](auto& to, auto& from) {
    to.insert(to.end(), std::make_move_iterator(from.begin()), std::make_move_iterator(from.end()));
  };
  move(destination.paths,source.paths); move(destination.frames,source.frames);
  move(destination.diagnostics,source.diagnostics);
}
}
std::optional<CliRequest> parse_request(const std::vector<std::string>& arguments) {
  const std::vector<std::string> flags = {
    "--header", "--instance", "--step", "--odbFile", "--suffix", "--format", "--writeHistory", "--writePVD"};
  std::unordered_map<std::string,std::vector<std::string>> values;
  for (std::size_t i = 0; i < arguments.size(); ++i) {
    const auto& argument = arguments[i];
    if (argument == "--help" || argument == "-h") return std::nullopt;
    const auto equal = argument.find('=');
    const auto flag = argument.substr(0, equal);
    bool known = false;
    for (const auto& candidate : flags) if (candidate == flag) known = true;
    if (!known) throw ArgumentError("Unrecognized argument: " + argument);
    if (values.count(flag)) throw ArgumentError("Repeated flag: " + flag);
    std::vector<std::string> items;
    if (equal != std::string::npos) items.push_back(argument.substr(equal + 1));
    const bool multiple = flag == "--instance" || flag == "--step";
    if (multiple) {
      while (i + 1 < arguments.size() && !option(arguments[i+1])) items.push_back(arguments[++i]);
    } else if (items.empty() && i + 1 < arguments.size() && !option(arguments[i+1])) {
      items.push_back(arguments[++i]);
    }
    if (items.empty()) throw ArgumentError("Missing value for " + flag);
    for (const auto& value : items)
      if (value.empty() && flag != "--suffix") throw ArgumentError("Empty value for " + flag);
    values.emplace(flag, std::move(items));
  }
  auto required = [&](const std::string& flag) -> const std::string& {
    const auto found = values.find(flag);
    if (found == values.end()) throw ArgumentError("Required argument: " + flag);
    return found->second.front();
  };
  auto single = [&](const std::string& flag, const std::string& fallback) {
    const auto found = values.find(flag);
    return found == values.end() ? fallback : found->second.front();
  };
  const bool header = boolean(required("--header"), "--header");
  const auto input = required("--odbFile");
  const bool history = boolean(single("--writeHistory", "0"), "--writeHistory");
  const bool collection = boolean(single("--writePVD", "0"), "--writePVD");
  const auto format = single("--format", "ascii");
  if (format != "ascii" && format != "binary") throw ArgumentError("--format must be ascii or binary");
  try {
    if (input.find('\0') != std::string::npos) throw ArgumentError("ODB path contains NUL");
    const auto path = std::filesystem::absolute(std::filesystem::u8path(input)).lexically_normal();
    if (!std::filesystem::is_regular_file(path)) throw ArgumentError("ODB file does not exist or is not a file: " + path.u8string());
    const auto outputs = OutputOptions::from_odb(path, single("--suffix", ""), false,
                                                format == "binary" ? VtuFormat::binary : VtuFormat::ascii);
    if (header) return CliRequest{path, ExportMode::header, std::nullopt, outputs, false};
    return CliRequest{path, collection ? ExportMode::collection : ExportMode::frames,
                       selection(values["--instance"], values["--step"]), outputs, history};
  } catch (const std::filesystem::filesystem_error& error) { throw ArgumentError(error.what()); }
  catch (const OutputError& error) { throw ArgumentError(error.what()); }
}
void print_help(std::ostream& out) {
  out << "Usage: ODB2VTK --header 0|1 --odbFile FILE [options]\n"
      << "Convert Abaqus ODB data to VTU, PVD, JSON and CSV.\n\n"
      << "  --header 0|1       1 writes header JSON; 0 exports selected data\n"
      << "  --odbFile FILE     Input ODB compatible with the installed SDK\n"
      << "  --instance NAME... Selected instance names, in output order\n"
      << "  --step STEP:0,1... Explicit frame lists, in output order\n"
      << "  --suffix TEXT      Suffix appended to the output name (default: empty)\n"
      << "  --format ascii|binary  ASCII or uncompressed appended raw (default: ascii)\n"
      << "  --writeHistory 0|1 Also export history CSV once (default: 0)\n"
      << "  --writePVD 0|1     1 indexes existing VTUs without conversion (default: 0)\n"
      << "  -h, --help         Show help without opening an ODB\n\n"
      << "Normal frame export writes no PVD. Use --writePVD 1 after frame export.\n"
      << "Statuses: 0 success, 2 arguments/selections, 1 runtime failure.\n";
}
ExportResult execute_request(const CliRequest& request, const SourceFactory& factory, Progress progress) {
  if (request.mode != ExportMode::header && request.mode != ExportMode::frames && request.mode != ExportMode::collection)
    throw ArgumentError("Invalid export mode");
  if (request.mode != ExportMode::header && !request.selection) throw SelectionError("Data export requires a selection");
  std::unique_ptr<Source> source;
  ExportResult result;
  try {
    source = factory(request.odb_file);
    if (!source) throw SourceError("Source factory returned no source");
    Exporter exporter(*source, std::move(progress));
    if (request.mode == ExportMode::header) append(result, exporter.export_header(request.outputs));
    else {
      if (request.mode == ExportMode::collection) exporter.validate_collection(*request.selection, request.outputs);
      else exporter.validate_frames(*request.selection, request.outputs);
      if (request.write_history) exporter.validate_history(*request.selection, request.outputs);
      if (request.write_history) append(result, exporter.export_history(*request.selection, request.outputs));
      if (request.mode == ExportMode::collection) append(result, exporter.export_collection(*request.selection, request.outputs));
      else append(result, exporter.export_frames(*request.selection, request.outputs));
    }
    source->close();
    source.reset();
  } catch (...) {
    const auto cause = std::current_exception();
    std::string message;
    try { std::rethrow_exception(cause); }
    catch (const ExportFailure& error) { append(result, error.result()); message = error.what(); }
    catch (const std::exception& error) { message = error.what(); }
    catch (...) { message = "Unknown execution failure"; }
    // Do not replace the originating error with a second close failure.
    try { if (source && !source->closed()) source->close(); } catch (...) {}
    source.reset();
    if (!result.paths.empty()) throw ExportFailure(std::move(message), std::move(result), cause);
    std::rethrow_exception(cause);
  }
  return result;
}
int cli_main(const std::vector<std::string>& arguments, const SourceFactory& factory,
             std::ostream& output, std::ostream& errors) {
  try {
    const auto request = parse_request(arguments);
    if (!request) { print_help(output); return 0; }
    const auto result = execute_request(*request, factory, [&](const ProgressEvent& event) {
      output << "Completed: " << event.path.u8string() << '\n';
      if (!output) throw OutputError("Cannot report progress");
    });
    for (const auto& diagnostic : result.diagnostics)
      errors << "Omitted " << diagnostic.field << ": " << diagnostic.message << '\n';
    return 0;
  } catch (const ArgumentError& error) { errors << "odb2vtk: " << error.what() << '\n'; return 2; }
  catch (const SelectionError& error) { errors << "odb2vtk: " << error.what() << '\n'; return 2; }
  catch (const ExportFailure& error) {
    errors << "odb2vtk: " << error.what() << '\n';
    if (!error.result().paths.empty()) {
      errors << "Completed before failure: ";
      for (std::size_t i = 0; i < error.result().paths.size(); ++i)
        errors << (i ? ", " : "") << error.result().paths[i].u8string();
      errors << '\n';
    }
    return 1;
  } catch (const std::exception& error) { errors << "odb2vtk: " << error.what() << '\n'; return 1; }
  catch (...) { errors << "odb2vtk: unknown failure\n"; return 1; }
}
}
