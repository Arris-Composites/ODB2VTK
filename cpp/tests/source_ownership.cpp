#include "odb2vtk_core/abaqus_source.hpp"
#include "odb2vtk_core/converter.hpp"
#include <filesystem>
#include <iostream>
#include <optional>
#ifdef _WIN32
#include <windows.h>
#endif

int main(int argc, char **argv) {
#ifdef _WIN32
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
#endif
  if (argc < 2 || argc > 3)
    return 2;
  try {
    using namespace odb2vtk_core;
    AbaqusSource source(argv[1]);
    const auto path = std::filesystem::absolute(argv[1]);
    AbaqusSource second(
        argc == 3 ? std::string(argv[2])
                  : (path.parent_path() / "." / path.filename()).string());
    const auto names = source.instance_names();
    const auto second_names = second.instance_names();
    std::optional<InstanceMesh> owned;
    if (!names.empty())
      owned = source.mesh(names[0]);
    source.close();
    source.close();
    if (!source.closed() || second.instance_names() != second_names)
      throw std::runtime_error("Surviving source invalidated");
    bool rejected = false;
    try {
      source.steps();
    } catch (const SourceError &) {
      rejected = true;
    }
    if (!rejected)
      throw std::runtime_error("Closed source accepted query");
    const auto steps = second.steps();
    std::optional<HistoryTable> history;
    if (!steps.empty())
      history = Converter(second).history(Selection({}, {{steps[0].name, {}}}));
    const auto missing = path.string() + ".source-contract-missing";
    if (std::filesystem::exists(missing))
      throw std::runtime_error("Missing-file fixture unexpectedly exists");
    rejected = false;
    try {
      AbaqusSource invalid(missing);
    } catch (const SourceError &) {
      rejected = true;
    }
    if (!rejected || second.instance_names() != second_names)
      throw std::runtime_error("Failed constructor damaged active source");
    second.close();
    if (owned && owned->coordinates.columns() != 3)
      throw std::runtime_error("Owned mesh invalid after closure");
    if (history && history->headers.size() != history->values.columns())
      throw std::runtime_error("Owned history invalid after closure");
    // Closing the last source from a synchronous visitor must not invalidate
    // the active SDK operation's local handles; further block delivery stops.
    AbaqusSource stream(argv[1]);
    std::optional<FieldBlock> retained;
    std::size_t visits = 0;
    if (!names.empty())
      for (const auto &step : stream.steps()) {
        if (!step.frame_count)
          continue;
        for (const auto &field : stream.field_names(step.name, 0)) {
          const auto info = stream.describe_field(step.name, 0, field, names);
          if (info.layout.position != "NODAL" &&
              info.layout.position != "INTEGRATION_POINT")
            continue;
          try {
            stream.field_blocks(step.name, 0, field, names[0],
                                info.layout.position, std::nullopt,
                                [&](FieldBlock block) {
                                  ++visits;
                                  retained.emplace(std::move(block));
                                  stream.close();
                                });
          } catch (const SourceError &) {
            if (!stream.closed())
              throw;
          }
          if (stream.closed())
            break;
        }
        if (stream.closed())
          break;
      }
    stream.close();
    if (visits > 1 ||
        (retained && retained->values.rows() != retained->labels.size()))
      throw std::runtime_error("Visitor closure/owned block contract failed");
    std::cout
        << "Native source ownership, recovery and retained records passed\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
